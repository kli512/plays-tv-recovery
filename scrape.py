import argparse
import logging
import os
import re
import threading
import time
import unicodedata
import urllib.request
from multiprocessing import Pool

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logging.basicConfig(level=logging.INFO)
base_url = 'https://web.archive.org/web/999999999999999999999/'

def slugify(value):
    """
    https://github.com/django/django/blob/master/django/utils/text.py
    """
    value = unicodedata.normalize('NFKD', value).encode(
        'ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


def scroll(driver, timeout=10, scroll_delay=2, log=False):
    """
    Scrolls to the bottom of an infinite scrolling Selenium web driver page
    """
    last_height = -1
    last_scroll_time = time.time()

    while True:
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            if time.time() - last_scroll_time > timeout:
                if log:
                    logging.info('Done scrolling!')
                return
        else:
            last_height = new_height
            last_scroll_time = time.time()
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")

            if log:
                logging.info('Scrolling...')

        time.sleep(scroll_delay)


def parse_tag(tag):
    """
    Parses src tag for the video url and name
    """
    page = re.match(r'.*?\?', tag['href']).group()[:-1]
    video_name = tag.decode_contents()

    return page, video_name


def process_tag(page_url, video_name, output_folder, video_number):
    """
    Downloads the requested page url with the video name in the output folder
    """
    try:
        logging.info(f'Downloading "{video_name}" from {page_url}')

        page = urllib.request.urlopen(base_url + page_url).read()
        soup = BeautifulSoup(page, features='html.parser')

        source_tag = soup.findAll('source', {'res': '720'})[0]

        urllib.request.urlretrieve(
            'http:' + source_tag['src'],
            os.path.join(output_folder, f'{slugify(video_name)}_{video_number}.mp4'))
    except:
        return False, video_name

    return True, video_name


if __name__ == '__main__':
    try:
        driver_path = os.path.join('./chromedriver/', os.listdir('./chromedriver/')[0])
    except IndexError:
        print('Please download the correct ChromeDriver for your OS and Chrome version and put it in ./chromedriver/')
        print('https://chromedriver.chromium.org/downloads')
        print('Make sure only the correct driver executable is in the folder.')
        exit(0)

    parser = argparse.ArgumentParser(
        description='Recover playstv plays from the Wayback Machine.')
    parser.add_argument('-u', '--username', type=str, required=True,
                        help='Username to recover',)
    parser.add_argument('-o', '--output-folder', type=str, required=True,
                        help='Output folder to videos')
    args = parser.parse_args()

    if not os.path.exists(args.output_folder):
        os.makedirs(args.output_folder)

    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('log-level=3')

    logging.info('Starting scraper!')
    driver = webdriver.Chrome(options=chrome_options,
                              executable_path=driver_path)
    driver.implicitly_wait(10)

    logging.info(f'Getting user profile {args.username}')
    driver.get(base_url + 'https://plays.tv/u/' + args.username)

    logging.info('Scrolling to find all videos...')
    scroll(driver, 10, log=True)
    soup = BeautifulSoup(driver.page_source, features='html.parser')
    driver.close()

    logging.info('Parsing user page html for videos...')
    content_div = soup.find('div', {'class': 'content-1'})
    link_tags = content_div.findAll('a',
        {
            'class': 'title',
            'href': re.compile(r'https://plays\.tv/video/[\da-f]+/.*')
        })

    logging.info(f'Found {len(link_tags)} videos')
    parsed_link_tags = [(*parse_tag(tag), args.output_folder, i)
                        for i, tag in enumerate(link_tags)]

    with Pool() as p:
        res = p.starmap(process_tag, parsed_link_tags)

    for success, video_name in res:
        if not success:
            logging.info(f'Was unable to download "{video_name}"')

    logging.info(
        f'Successfully downloaded {sum(success for success, _ in res)}/{len(link_tags)} videos')
