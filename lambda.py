import asyncio
import aiohttp
import boto3
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import json
from tqdm import tqdm
from collections import defaultdict

def get_pdf_urls_from_page(base_url):
      try:
            response = requests.get(base_url)
            response.raise_for_status()
      except Exception as e:
            return {"statusCode": 500, "body": f"Failed to fetch URL: {e}"}
      
      soup = BeautifulSoup(response.text, 'html.parser')
      listsoup = soup.find('ul', class_='list-unstyled')
      items_list = listsoup.find_all('p', class_="pull-left")
      
      pattern = r"Erschienen: (\d{2}\.\d{2}\.\d{4})"
      pdf_links = [{'pub_date' :  match.group(1).strip(), 'doc' : p.find('a', href=True)} for p in items_list\
            if "Dateityp: PDF" in p.get_text(separator=" ", strip=True) and (match := re.search(pattern, p.get_text(separator=" ", strip=True)))]
      
      return pdf_links

def get_metadata_pdf(pdf_link):
      metadata_link = defaultdict()
      a = pdf_link['doc']
      metadata_link['pub_date'] = pdf_link['pub_date']
      metadata_link['date_type'] = 'pdf'
      metadata_link['href'] = a['href']
      metadata_link['title'] = re.search(r"\'([^']*?)\'", a['title']).group(1)
      metadata_link['lan'] = a.get_text(strip=True)
      return metadata_link
      
def get_next_page_url(url):
      try:
            response = requests.get(url)
            response.raise_for_status()
      except Exception as e:
            return {"statusCode": 500, "body": f"Failed to fetch URL for next page : {e}"}

      soup = BeautifulSoup(response.text, 'html.parser')
      items = soup.find('nav', class_='pagination-container clearfix').find_all('li', class_='separator-left')
      if items:
            next_page_url = []
            for item in items:
                  next_page_url.append(item.find('a', href=True)['href'])
      else:
            print(f'no item found for {url}')
      if next_page_url:
            return next_page_url[0]
      else:
            return None
      
def get_pages_number():
      first_page = "https://www.bfe.admin.ch/bfe/de/home/news-und-medien/publikationen.exturl.html/aHR0cHM6Ly9wdWJkYi5iZmUuYWRtaW4uY2gvZGUvc3VjaGU_eD/0x.html"
      try:
            response = requests.get(first_page)
            response.raise_for_status()
      except Exception as e:
            return {"statusCode": 500, "body": f"Failed to fetch URL for next page : {e}"}
      
      soup = BeautifulSoup(response.text, 'html.parser')
      text = soup.find('nav', class_='pagination-container clearfix').find('span').get_text(strip=True)
      return int(re.search(r"von ([\d\.,]+)", text).group(1).strip())
      
                  

if __name__=="__main__":
      base_url = "https://www.bfe.admin.ch"
      first_p = "https://www.bfe.admin.ch/bfe/de/home/news-und-medien/publikationen.exturl.html/aHR0cHM6Ly9wdWJkYi5iZmUuYWRtaW4uY2gvZGUvc3VjaGU_eD/0x.html"
            
      n = get_pages_number()
      
      
# def lambda_handler(event, context):
#       url = event.get('url')
#       if not url:
#             return {'Status code': 400, 'body': 'Missing url'}
