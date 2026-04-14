#  ICAIDashboard

##  Live Dashboard
**[View the Live ICAI Analytics Dashboard Here](https://app.powerbi.com/view?r=eyJrIjoiZDMyMjgxMDItMGM1MS00M2U3LWI5NTktZjI3ZTY3OTU5ZTA2IiwidCI6IjhlNjhlNzdlLWUxOTMtNDI3MC04Mzg1LTJjOWViNTgxYjNiNiJ9)**

---

##  The Problem
The official ICAI portal is built on legacy ASP.NET architecture. To find batch details, users have to manually click through multiple dropdowns for every region and city. This makes it impossible to get a "big picture" view of availability or export data for personal tracking.

## The Solution (Automated Pipeline)
I built an automated pipeline that turns this manual process into a live dataset.

### 1. Data Extraction (The Scraper)
* **Engine:** Built with **Python + aiohttp** for high-speed asynchronous scraping.
* **Complexity:** It programmatically handles ASP.NET `__VIEWSTATE` and `__EVENTVALIDATION` tokens to navigate the portal's postback logic.
* **AI Disclosure:** The core logic for `scraper.py` was generated via AI prompting and then manually refined to handle the specific site structure and concurrency limits.

### 2. Automation (GitHub Actions)
* **Schedule:** A GitHub Action triggers the scraper every **3 hours**.
* **Sync:** The script scrapes fresh data, converts it to CSV, and automatically pushes the update back to this repository.

### 3. Geo-Mapping
* The raw scraped data is joined with `spatialdata.csv` (containing Latitude/Longitude) to enable geographical mapping and heatmaps in the final dashboard.

### 4. Visualization (Power BI)
* The **Power BI Service** is linked to the "Raw" CSV file in this repo. Whenever the file updates on GitHub, the dashboard refreshes, providing a real-time view of batch availability across India.

---

##  Repository Blueprint
| File | Purpose |
| :--- | :--- |
| `scraper.py` | The main engine that crawls the portal. |
| `icai_async_data.csv` | The live, auto-updating dataset. |
| `spatialdata.csv` | Mapping file for city coordinates. |
| `requirements.txt` | Python dependencies (Pandas, BeautifulSoup, etc). |

---

### Local Setup
If you want to run the scraper manually:
1. Clone the repo.
2. Install requirements: `pip install -r requirements.txt`.
3. Run: `python scraper.py`.
