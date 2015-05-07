# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html

import json

class GetcarsPipeline(object):
    MySep = '^^^'
    def __init__(self):
#         self.file = open('items.json', 'wb')
        self.file = open('items.txt', 'w')

    def process_item(self, item, spider):
#         line = json.dumps(dict(item))  
#         self.file.write(line)
#         return item
        for acarname in item['carname']:
            self.file.write("carname is " + acarname[0:-1] + '\t')
            
        self.file.write(self.MySep)
        
        self.file.write("price is ")
        i = 0
        for aprice in item['price']:
            i = i + 1
            if(i == 2):
                self.file.write('--')
            self.file.write(aprice)
        self.file.write('\t')
            
        self.file.write(self.MySep)
        
        self.file.write("star is ")
        
        if(len(item['stars'])==0):
            self.file.write("MISSING")
        else:        
            for astar in  item['stars']:
                self.file.write(astar)
                
        self.file.write("\n")
        return item
