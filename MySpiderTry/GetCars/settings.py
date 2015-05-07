# -*- coding: utf-8 -*-

# Scrapy settings for GetCars project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/en/latest/topics/settings.html
#

BOT_NAME = 'GetCars'

SPIDER_MODULES = ['GetCars.spiders']
NEWSPIDER_MODULE = 'GetCars.spiders'

# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = 'GetCars (+http://www.yourdomain.com)'

ITEM_PIPELINES = ['GetCars.pipelines.GetcarsPipeline']

