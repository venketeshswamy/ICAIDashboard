# --- STEP 1: Install necessary libraries (Run this once in Colab) ---
!pip install nest_asyncio aiohttp pandas beautifulsoup4

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import pandas as pd
import sys
import nest_asyncio  # Import nest_asyncio

# --- APPLY THE FIX ---
# This patches the Colab event loop to allow nested asyncio.run calls
nest_asyncio.apply()

# --- Configuration ---
URL = "https://www.icaionlineregistration.org/LaunchBatchDetail.aspx"
OUTPUT_FILE = "icai_async_data_v5.csv"
CONCURRENT_LIMIT = 150 

# Common Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Referer": URL,
    "Origin": "https://www.icaionlineregistration.org",
    "Content-Type": "application/x-www-form-urlencoded"
}

class ICAIAsyncScraper:
    def __init__(self):
        self.all_data = []
        # Semaphore is created in run() to avoid loop mismatch errors

    def get_soup(self, html):
        return BeautifulSoup(html, 'html.parser')

    def extract_hidden_fields(self, soup):
        """Extracts __VIEWSTATE, __EVENTVALIDATION etc."""
        payload = {}
        for tag in soup.find_all('input', type='hidden'):
            if tag.get('name'):
                payload[tag['name']] = tag.get('value', '')
        return payload

    def find_field_names(self, soup):
        """Locate dynamic IDs"""
        names = {}
        selects = soup.find_all('select')
        if len(selects) >= 3:
            names['region'] = selects[0]['name']
            names['pou'] = selects[1]['name']
            names['course'] = selects[2]['name']
        
        btn = soup.find('input', {'value': 'Get List'})
        if not btn: btn = soup.find('input', type='submit')
        names['btn'] = btn['name'] if btn else None
        return names

    async def fetch_regions(self, session):
        """Phase 1: Get list of Regions"""
        print("[*] Phase 1: Fetching Regions...")
        async with session.get(URL) as resp:
            text = await resp.text()
            soup = self.get_soup(text)
            fields = self.find_field_names(soup)
            
            reg_select = soup.find('select', {'name': fields['region']})
            regions = [(o['value'], o.text.strip()) for o in reg_select.find_all('option') 
                       if o['value'] and "Select" not in o.text]
            return regions, fields

    async def fetch_pous_for_region(self, region_tuple, fields):
        """Phase 2: Get POUs for a specific region"""
        reg_val, reg_name = region_tuple
        
        async with self.semaphore: 
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                try:
                    # 1. Load Page 
                    async with session.get(URL) as resp:
                        soup = self.get_soup(await resp.text())
                        payload = self.extract_hidden_fields(soup)

                    # 2. Select Region
                    payload[fields['region']] = reg_val
                    payload['__EVENTTARGET'] = fields['region']
                    payload['__EVENTARGUMENT'] = ''
                    
                    async with session.post(URL, data=payload) as resp:
                        soup = self.get_soup(await resp.text())
                        pou_select = soup.find('select', {'name': fields['pou']})
                        
                        if not pou_select:
                            return []

                        pous = [(o['value'], o.text.strip()) for o in pou_select.find_all('option') 
                                if o['value'] and "Select" not in o.text]
                        
                        print(f"    [+] Region '{reg_name}' has {len(pous)} POUs")
                        return [(region_tuple, (p_val, p_text)) for p_val, p_text in pous]
                except Exception as e:
                    print(f"    [!] Error fetching POUs for {reg_name}: {e}")
                    return []

    async def scrape_pou_combination(self, combo, fields):
        """Phase 3: Scrape data for a single Region-Pou pair"""
        (reg_val, reg_name), (pou_val, pou_name) = combo
        
        async with self.semaphore:
            try:
                async with aiohttp.ClientSession(headers=HEADERS) as session:
                    # -- Step A: Init Session --
                    async with session.get(URL) as resp:
                        soup = self.get_soup(await resp.text())
                        current_payload = self.extract_hidden_fields(soup)

                    # -- Step B: Select Region --
                    current_payload[fields['region']] = reg_val
                    current_payload['__EVENTTARGET'] = fields['region']
                    current_payload['__EVENTARGUMENT'] = ''
                    
                    async with session.post(URL, data=current_payload) as resp:
                        text = await resp.text()
                        soup = self.get_soup(text)
                        current_payload = self.extract_hidden_fields(soup) 

                    # -- Step C: Select POU --
                    current_payload[fields['region']] = reg_val 
                    current_payload[fields['pou']] = pou_val    
                    current_payload['__EVENTTARGET'] = fields['pou']
                    current_payload['__EVENTARGUMENT'] = ''

                    async with session.post(URL, data=current_payload) as resp:
                        text = await resp.text()
                        soup = self.get_soup(text)
                        current_payload = self.extract_hidden_fields(soup) 

                        # Identify Courses 
                        course_select = soup.find('select', {'name': fields['course']})
                        courses = [(o['value'], o.text.strip()) for o in course_select.find_all('option') 
                                   if o['value'] and "Select" not in o.text]

                    # -- Step D: Iterate Courses --
                    for course_val, course_name in courses:
                        # Prepare "Get List" Payload
                        final_payload = current_payload.copy()
                        final_payload[fields['region']] = reg_val
                        final_payload[fields['pou']] = pou_val
                        final_payload[fields['course']] = course_val
                        final_payload['__EVENTTARGET'] = ''
                        final_payload['__EVENTARGUMENT'] = ''
                        if fields['btn']:
                            final_payload[fields['btn']] = 'Get List'
                        
                        async with session.post(URL, data=final_payload) as resp:
                            soup_final = self.get_soup(await resp.text())
                            self.parse_table(soup_final, reg_name, pou_name, course_name)
                            
                    print(f"    [OK] Scraped {pou_name} ({len(courses)} courses)")

            except Exception as e:
                print(f"    [!] Failed {reg_name}-{pou_name}: {e}")

    def parse_table(self, soup, reg, pou, course):
        """Helper to extract table data, handling dynamic columns"""
        table = soup.find('table', id=lambda x: x and 'Grid' in x)
        if not table: table = soup.find('table', border='1')
        
        if table:
            rows = table.find_all('tr')
            for row in rows[1:]:
                cols = row.find_all('td')
                if not cols or "No records" in row.text: continue
                
                c = [ele.text.strip() for ele in cols]
                
                while len(c) < 9: c.append('')
                
                self.all_data.append({
                    'Region': reg,
                    'Pou': pou,
                    'Selected_Course': course,
                    'Batch No': c[0],
                    'Available Seats': c[1],
                    'From Date': c[2],
                    'To Date': c[3],
                    'Batch Time': c[4],
                    'Pou Name': c[5],
                    'Course': c[6],
                    'Open For': c[7],
                    'Registration Start Date': c[8] 
                })

    async def run(self):
        # Create Semaphore INSIDE the async loop
        self.semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
        
        print(f"[*] Starting Async Scraper with {CONCURRENT_LIMIT} workers...")
        
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # 1. Get Regions
            regions, fields = await self.fetch_regions(session)
            print(f"[*] Found {len(regions)} Regions: {[r[1] for r in regions]}")

            # 2. Get POUs
            print("[*] Phase 2: Mapping all POUs...")
            tasks = [self.fetch_pous_for_region(r, fields) for r in regions]
            results = await asyncio.gather(*tasks)
            
            # Flatten list of lists
            all_combos = [item for sublist in results for item in sublist]
            print(f"[*] Total Combinations to scrape: {len(all_combos)}")

            # 3. Scrape Data
            print("[*] Phase 3: Scraping Batch Data...")
            scrape_tasks = [self.scrape_pou_combination(combo, fields) for combo in all_combos]
            await asyncio.gather(*scrape_tasks)
            
            # Save
            if self.all_data:
                df = pd.DataFrame(self.all_data)
                df.to_csv(OUTPUT_FILE, index=False)
                print(f"\n[*] DONE! Scraped {len(self.all_data)} rows. Saved to {OUTPUT_FILE}")
            else:
                print("\n[!] No data found.")

# --- ENTRY POINT ---
if __name__ == "__main__":
    scraper = ICAIAsyncScraper()
    # Google Colab is Linux-based, so Windows loop policy is irrelevant here.
    # nest_asyncio.apply() handled the loop conflict.
    asyncio.run(scraper.run())
