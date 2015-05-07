from scrapy.spider import Spider
from scrapy.selector import Selector

from GetCars.items import CarsInfo


class CarsSpider(Spider):
    name = "cars"
    allowed_domains = ["www.cars.com"]
    start_urls = [
        "http://www.cars.com/guides/sedan/all/",
        "http://www.cars.com/guides/suv/all/",
        "http://www.cars.com/guides/luxury-car/all/",
        "http://www.cars.com/guides/sports-car/all/",
        "http://www.cars.com/guides/truck/all/",
        "http://www.cars.com/guides/crossover/all/",
        "http://www.cars.com/guides/wagon-hatchback/all/",
        "http://www.cars.com/guides/minivan-van/all/",
        "http://www.cars.com/guides/convertible/all/",
        "http://www.cars.com/guides/coupe/all/",
        "http://www.cars.com/guides/best-gas-mileage/all/",
    ]

    def parse(self, response):
        '''
        The lines below is a spider contract. For more info see:
        http://doc.scrapy.org/en/latest/topics/contracts.html

        @url http://www.dmoz.org/Computers/Programming/Languages/Python/Resources/
        @scrapes name
        '''
        sel = Selector(response)
       ## sites = sel.xpath('//ul[@class="directory-url"]/li')
        
        carinfoall = sel.xpath('//*[@id="vehicleRow"]/div[2]/div[@class = "row vehicle"]')
        
        items = []
        for acar in carinfoall:
            item = CarsInfo()
            item['carname'] =acar.xpath('div[3]/div[1]/div[1]/h4/a/text()').re('([\s\S]*[\n])')
            #item['carname'] is a list, and the elements in it is a unicode
            item['price'] = acar.xpath('div[3]/div[1]/div[2]/strong/text()').re('(\$[0-9]*[,][0-9]*)')   
            item['stars'] = acar.xpath('div[3]/div[2]/div/div[1]/div[2]/text()').re('([0-9][.][0-9])')

            items.append(item)

        return items
