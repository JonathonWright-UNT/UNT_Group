import requests
from bs4 import BeautifulSoup
import re


def getBookDetails(isbn):

    #(scraping) insert isbn into url to navigate to page with book info
    url = f"https://www.bookfinder.com/search/?author=&title=&lang=en&isbn={str(isbn)}&new_used=*&destination=us&currency=USD&mode=basic&st=sr&ac=qr"

    results = {}

    #scraping
    page = requests.get(url)
    soup = BeautifulSoup(page.content, 'html.parser')

    imgCover = soup.find(id='coverImage')

    title = soup.find(id='describe-isbn-title')

    publisher = soup.find(itemprop='publisher')

    author = soup.find(itemprop='author')

    try:
        results.update({'imgCover': imgCover.get('src'),
                        'title': title.contents[0],
                        'publisher': publisher.contents[0],
                        'author': author.contents[0]})
    
    # return none if isbn not recognized
    except Exception as e:
        return None
    

    return results
