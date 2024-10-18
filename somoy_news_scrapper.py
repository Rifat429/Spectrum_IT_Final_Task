import re
import json
from datetime import datetime, timedelta, timezone
from transformers import pipeline
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.webdriver import WebDriver


def analyze_article(paragraph):
    # Step 1: Load pre-trained models (inside the function)
    ner_pipeline = pipeline("ner", model="dbmdz/bert-large-cased-finetuned-conll03-english")
    sentiment_pipeline = pipeline("sentiment-analysis")

    # Step 2: Extract named entities (keywords)
    entities = ner_pipeline(paragraph)
    keywords = [entity['word'] for entity in entities]

    # Step 3: Initialize variables to check for Bangladesh and other countries
    countries = []
    bangladesh_mentioned = False
    bangladesh_mentions = 0
    other_countries_mentions = 0

    # Step 4: Function to check if an entity is a country
    def is_country(entity):
        country_keywords = ['Bangladesh', 'America', 'India', 'China', 'Japan', 'Germany', 'France', 'Italy', 'UK', 'Canada']
        # Add other countries as needed
        return any(country in entity for country in country_keywords)

    # Step 5: Process entities to find countries and check for Bangladesh
    for entity in entities:
        word = entity['word']
        if is_country(word):
            countries.append(word)
            if 'Bangladesh' in word:
                bangladesh_mentioned = True
                bangladesh_mentions += 1
            else:
                other_countries_mentions += 1

    # Step 6: Check if there is an international perspective
    international_perspective = bangladesh_mentioned and len(countries) > 1

    # Step 7: Perform sentiment analysis on the paragraph
    sentiment_result = sentiment_pipeline(paragraph)
    sentiment = sentiment_result[0]['label']  # 'POSITIVE', 'NEGATIVE', or 'NEUTRAL'

    # Step 8: Calculate the news importance score
    news_score = 0
    if bangladesh_mentioned:
        # Base score for mentions of Bangladesh
        news_score += bangladesh_mentions * 2

        # Add score for other countries if Bangladesh is mentioned
        news_score += other_countries_mentions * 1

        # Adjust score based on sentiment
        if sentiment == 'POSITIVE':
            news_score *= 1.1  # Slight boost for positive news
        elif sentiment == 'NEGATIVE':
            news_score *= 0.9  # Slight reduction for negative news

    # Step 9: Return the results
    return {
        "keywords": keywords,
        "international_perspective": international_perspective,
        "sentiment": sentiment,
        "news_importance_score": round(news_score, 2)
    }


def is_old_news(created_at: datetime):
    if not created_at.tzinfo:
        # If created_at is offset-naive, assume it's in UTC
        created_at = created_at.replace(tzinfo=timezone.utc)

    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)

    return created_at < three_days_ago


def get_news_urls(dr: WebDriver, url: str, url_pattern: re.Pattern[str] | None) -> [str]:
    dr.get(url)

    # Step 3: Get all news URLs
    news_elements = dr.find_elements(By.CSS_SELECTOR, 'a')
    news_urls = [
        element.get_attribute('href') for element in news_elements
        if element.get_attribute('href') and (url_pattern.match(element.get_attribute('href') if url_pattern else True))
    ]

    news_urls = list(set(news_urls))

    print("News URLs found:")
    return news_urls


def get_news_data(dr: WebDriver, url: str, url_pattern: re.Pattern[str] | None, category: tuple[str, str]) -> [str]:
    if url_pattern and not url_pattern.match(url):
        return None

    news_data = {
        'url': url,
    }

    dr.get(url)

    news_data['title'] = dr.title
    meta_description = dr.find_element(By.XPATH, "//meta[@name='description']")
    news_data['meta_description'] = meta_description.get_attribute("content")

    unprocessed_data = dr.find_element(By.XPATH, "//script[@type='application/ld+json']")
    unprocessed_data = unprocessed_data.get_attribute("innerText")
    unprocessed_data = json.loads(unprocessed_data)

    # news_type
    news_element = dr.find_element(By.XPATH, "//div[@id='news1']")
    news_data['news_type'] = news_element.find_elements(By.CSS_SELECTOR, 'a')[0].find_elements(By.CSS_SELECTOR, 'span')[0].get_attribute("innerText")

    if news_data['news_type'] != category[1].upper():
      return None

    # news_sub_category
    # media_type
    news_data['media_type'] = unprocessed_data.get('@type')
    # image_url
    news_data['image_url'] = unprocessed_data.get('image').get('url')
    # published_date
    news_data['published_date'] = unprocessed_data.get('datePublished')
    # updated_date
    news_data['updated_date'] = unprocessed_data.get('dateModified')
    # source
    news_data['source'] = dr.find_element(By.XPATH, "//meta[@name='author']").get_attribute("content")

    # last_scraped
    news_data['last_scraped'] = datetime.now().isoformat()
    # old (bool) if older than 3 days
    news_data['old'] = is_old_news(datetime.fromisoformat(news_data['published_date']))
    # views = 0
    news_data['views'] = 0
    # rating = 0
    news_data['rating'] = 0
    # engagement = 0
    news_data['engagement'] = 0
    # author
    news_data['author'] = unprocessed_data.get('author').get('name')

    # content
    news_data['content'] = unprocessed_data.get('description')

    news_data.update(analyze_article(news_data['content']))

    return news_data


category_map = {
    1: ('bangladesh', 'Bangladesh'),
    2: ('politics', 'Politics'),
    3: ('international', 'International'),
    4: ('sports', 'Sports'),
    5: ('entertainment-lifestyle', 'Entertainment & Lifestyle'),
    6: ('health', 'Health'),
    7: ('business', 'Business'),
    8: ('jobs', 'Jobs'),
    9: ('science-tech', 'Science & Tech'),
    10: ('education', 'Education'),
    11: ('weather', 'Weather'),
    12: ('environment-and-climate-crisis', 'Environment and Climate Crisis'),
    13: ('power-energy', 'Power & Energy'),
}


def main():
    print("please enter a category to scrape news from https://en.somoynews.tv (1-13)")
    print("1. bangladesh\
    2. politics\
    3.international\
    4. sports\
    5. entertainment-lifestyle\
    6. health\
    7. business\
    8. jobs\
    9. science-tech\
    10. education\
    11. weather\
    12. environment-and-climate-crisis\
    13. power-energy")

    category_id = int(input())

    if not category_map.get(category_id, None):
      print("invalid category")
      return

    print("starting scrapping process.")

    url = f"https://en.somoynews.tv/categories/{category_map[category_id][0]}"
    url_pattern = re.compile(r'https://en\.somoynews\.tv/news/\d{4}-\d{2}-\d{2}/[A-Za-z0-9]+')

    news_data_list = []

    try:
        print("initialize selenium webdriver...")
        dr = webdriver.Edge()

        print("getting news urls...")
        news_urls = get_news_urls(dr, url, url_pattern)

        print("getting news data...")

        for news_url in news_urls:
            news_data = get_news_data(dr, news_url, url_pattern, category_map[category_id])
            if news_data:
                news_data_list.append(news_data)

        print("news data scrapped!")
        dr.close()

        print("creating json file.")
        json_data = json.dumps(news_data_list)
        with open("data.json", "w") as f:
            f.write(json_data)

        print("done.")

    except Exception as e:
        print(e)


if __name__ == "__main__":
    main()