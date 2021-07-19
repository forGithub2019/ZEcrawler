# coding=utf-8

## todo  
#       v3:
#       [done]1 click to change page not use url (for fast)
#       [done]2 divide by time(scantime get from the last data  app:'citrix'+before:"2020-05-06")
#       [done]3 mutil thread
#       v4:
#       [done]4 remove browsermobproxy (because need capture the cube_authorization)
import sys
from logging import NullHandler, log
from sys import prefix
from time import sleep
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import urllib
import os
import re
import pymongo
from threading import Thread
import time
#import browsermobproxy
import random

PROCESSES_NUM = 4

VIEWNUM = 400   #num of entries one search can view

MONGO_URL = 'localhost'
MONGO_DB = 'ZOOMEYE_DB'
MONGO_TABLE = 'test'

client = pymongo.MongoClient(MONGO_URL)
db = client[MONGO_DB]

# proxyServer = browsermobproxy.Server(r'C:\\Users\\aaa\Desktop\\browsermob-proxy-2.1.4\\bin\\browsermob-proxy.bat')
# proxyServer.start()
# proxy = proxyServer.create_proxy()
# proxy.new_har('myHar',options={'captureHeaders':True, 'captureContent':True})
#proxy.headers({"test":1234, 'aaaaa':'ddddd'})

#USER_DATA_DIR = r'C:\\Users\\aaa\AppData\\Local\\Google\\Chrome\\'
USER_DATA_DIR = r'C:\\Users\\aaa\AppData\\Local\\Google\\Chrome\\mydata\\'
USER_DATA_DIR = os.getenv("localappdata")+r'\\Google\\Chrome\\mydata\\'

options = webdriver.ChromeOptions()
#options.add_argument('--proxy-server={0}'.format(proxy.proxy))   #设置代理
options.add_argument('--ignore-certificate-errors')
options.add_argument('--user-data-dir='+USER_DATA_DIR+"User Data")
options.add_experimental_option("excludeSwitches", ["enable-logging"])   #for去掉错误提示信息：bluetooth_adapter_winrt.cc:1072 Getting Default Adapter failed
prefs = {"profile.managed_default_content_settings.images": 2}   #设置无图模式
#option.add_experimental_option("prefs", prefs)                  #加载无图模式设置
#option.add_argument("--headless")                               #设置无头模式(不显示浏览器)

cube_authorization = None

myDriver = webdriver.Chrome(chrome_options=options)

SEARCHSTRS = []
datacount = 0
webdriverwait = None
blocks = []     # {'dealed':False, 'earliest_scan_time':""}
#driverList = [{'driver':myDriver,'available':True}]        # use for multiple processes
       
USERNAME = None
PASSWORD = None

def myerrlog(str):
    with open('error.log','a') as f:
        print('[errlog]:'+str)
        f.write(str+"\n")

def save_to_mongo(myfilter,result):
    global datacount
    try:
        #print("table:"+MONGO_TABLE)
        db[MONGO_TABLE].update_one(myfilter,{'$set':result},upsert = True) 
        datacount += 1
        # with open("res.txt",'a') as f:
        #     f.write("############################\n")
        #     for i in result.keys():
        #         f.write(i+": "+result[i]+"\n")
    except Exception as e:
        print('save to DB faild!\n'+str(e))

def login(loginUrl:str,myDriver = myDriver):
    global cube_authorization
    try:
        webdriverwait = WebDriverWait(myDriver, 10)  #timeout 30s
        if ('https://sso.telnet404.com/cas/login' not in myDriver.current_url):
            myDriver.get(loginUrl)
        if (myDriver.current_url =='https://www.zoomeye.org/'):
            return True
        list_DIV = webdriverwait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR,'#login_form > div.form-group')))
        input_username = list_DIV[0].find_element_by_css_selector('input')
        input_username.clear()
        input_username.send_keys(USERNAME)

        input_password = webdriverwait.until(EC.presence_of_element_located((By.CSS_SELECTOR,'#inputPassword')))
        input_password.clear() 
        input_password.send_keys(PASSWORD) 
        
        input_captcha = myDriver.find_element_by_id("id_captcha_1")
        input_captcha.clear()
        input_captcha.click()

        #myDriver.execute_script("arguments[0].focus();", input_captcha)
        while (1):
            if (len(input_captcha.get_attribute("value")) == 4 ):
                #print("iii:"+input_username.get_attribute("value"))
                if (input_username.get_attribute("value") != USERNAME):
                    input_username.clear()
                    input_username.send_keys(USERNAME) 
                if (input_password.get_attribute("value") != PASSWORD):
                    input_password.clear()
                    input_password.send_keys(PASSWORD) 
                button = myDriver.find_elements_by_tag_name("button")[0]
                button.click()
            else:
                sleep(0.5)

    except Exception as e:
        print(e)
        if ('https://sso.telnet404.com/cas/login' not in myDriver.current_url):  #means login success
            # for entry in proxy.har['log']['entries']:
            #     for header in entry['request']['headers']:
            #         if 'Cube-Authorization' in header['name']:
            #             cube_authorization = header['value']
            #             print("cube-authorization:"+header['value'])
            #             proxy.headers({"cube_authorization":cube_authorization})
            #             return True
            return True
        sleep(3)
        login(loginUrl)

def getOnePageInfo(searchurl : str, curpage : int, blockindex : int, processDriver):
    nextPageButton = None
    earliest_scan_time = ""
    global blocks
    try:
        print("searching: "+searchurl)
        if ("www.zoomeye.org/error/403" in processDriver.current_url):
            myerrlog("getOnePageInfo() 403 err!")
            return -1
        if (searchurl != processDriver.current_url):
            print("need get()~~ "+str(curpage))
            sleep(3)
            processDriver.get(searchurl)                # get() will stuck until the whole page loaded
        webdriverwait = WebDriverWait(processDriver, 30)
        search_result_list = webdriverwait.until(EC.presence_of_element_located((By.CSS_SELECTOR,'div.search-result-list')))
        #resdiv = webdriverwait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR,'div.search-result-item clearfix')))
        #search_result_item_clearfixs = processDriver.find_element_by_class_name("search-result-list").find_elements_by_class_name("clearfix")
        search_result_item_clearfixs = search_result_list.find_elements_by_class_name("clearfix")
        nextPageButton = search_result_item_clearfixs[-1].find_elements_by_tag_name('li')[-2]
        if nextPageButton.get_attribute("title") not in ['Next Page', '下一页']:
            nextPageButton = None
        products = []
        for search_result_item_clearfix in search_result_item_clearfixs[:-1]:
            search_result_item_info = search_result_item_clearfix.find_element_by_css_selector(".search-result-item-info")
            port_href = search_result_item_info.find_element_by_css_selector("div.search-result-tags > a").get_attribute("href")
            port_href = urllib.parse.unquote(port_href)
            reg_port = re.findall(r"port:\"([0-9]+)\"",port_href)
            port =reg_port[0] if len(reg_port)>0 else ''
            targetprotocol =re.findall(r"service:\"(.+)\"",port_href)[0] if len(re.findall(r"service:\"(.+)\"",port_href))>0 else ''
            
            location = search_result_item_info.find_element_by_css_selector("p > span.search-result-location").text
            reg_location = re.findall(r"[\"\']?([^,，]+),?(.*)[\"\']?",location)
            if len(reg_location)>0:
                country = reg_location[0][0]
                city = reg_location[0][1]
            else:
                country = ''
                city = ''
            scantime = search_result_item_info.find_element_by_css_selector("p.search-result-icon-time").text if search_result_item_info.find_element_by_css_selector("p.search-result-icon-time")!= None else ''
            st = time.strptime(scantime,'%Y-%m-%d %H:%M')
            earliest_scan_time = time.strftime('%Y-%m-%d',st)
            #print(st)
            a_elements = search_result_item_info.find_elements_by_css_selector("a")
            isp = ''
            for aa in a_elements:
                tmp = urllib.parse.unquote(aa.get_attribute('href'))
                restr = re.findall(r"isp:[\"\'](.+)[\"\']",tmp)
                if len(restr)>0:
                    isp = restr[0]

            detail = ''
            plist = search_result_item_info.find_elements_by_css_selector("p")
            for p in plist:
                detail += p.text + '\n'
            
            pres = search_result_item_clearfix.find_elements_by_css_selector("pre")
            for pre in pres:
                detail += "banner/Certificate:\n" + pre.text
                
            product={
                    'ip':search_result_item_clearfix.find_element_by_css_selector(".search-result-item-info > h3 > a").text,
                    'port':port,
                    'protocol':targetprotocol,
                    'isp':isp,
                    'scan_time':scantime,
                    'country':country,
                    'city':city,
                    'detail':detail
                }
            save_to_mongo({"ip":product['ip'], 'port':product['port']}, product)
        if blocks[blockindex]['earliest_scan_time'] == '':
            blocks[blockindex]['earliest_scan_time'] = earliest_scan_time
        try :
            if nextPageButton!=None:
                nextPageButton.click()
        except Exception:
            None
    except Exception as e:
        print("err in getOnePageInfo\n"+str(e))
        sleep(5)
        if ('https://sso.telnet404.com/cas/login' in processDriver.current_url):  #means login success
            login('https://sso.telnet404.com/cas/login',processDriver)
        if blocks[blockindex]['earliest_scan_time'] == '':
            blocks[blockindex]['earliest_scan_time'] = earliest_scan_time
        if nextPageButton!=None:
            nextPageButton.click()
        return 

def searchOneBlock(searchstr : str, processDriver : webdriver, blockIndex, pagenum = VIEWNUM//20):
    global blocks
    suffix = "&page={0}&pageSize=20"    #pageSize=50 no use
    prefix = 'https://www.zoomeye.org/searchResult?q='+urllib.parse.quote(searchstr)
    while (blocks[blockIndex]['earliest_scan_time'] == '' and pagenum > 1):   # 为获取blocks的earliest_scan_time重复get第20页数据5次，如果都失败，就try 19页，以此类推
        tryTimes = 5
        while (blocks[blockIndex]['earliest_scan_time'] == '' and tryTimes > 0):
            tryTimes -= 1
            res = getOnePageInfo(prefix + suffix.format(pagenum), pagenum, blockIndex, processDriver)  #deal last page in order to generate earliest_scan_time
            if (res == -1):
                return -1
        pagenum -= 1
    for curpage in range(1,pagenum):
        sleep(random.randint(15,30))
        #os.system("pause")
        res = getOnePageInfo(prefix + suffix.format(curpage), curpage, blockIndex, processDriver)
        if (res == -1):
                return -1

def searchProcess(searchstr : str, threadID):
    global blocks
    global blocksNum
    global starttime
    global datacount
    searchoption = webdriver.ChromeOptions()
    searchoption.add_argument('--ignore-certificate-errors')
    print("process[{0}]copying user cookie files...".format(threadID))
    thread_USER_DATA_DIR = USER_DATA_DIR+ "User Data{0}".format(threadID)
    os.system("rmdir /s/q \"{}\"".format(thread_USER_DATA_DIR))
    os.system("mkdir \"{}\"".format(thread_USER_DATA_DIR))
    os.system('xcopy /e/i/q "{0}" "{1}" '.format(USER_DATA_DIR+'User Data',thread_USER_DATA_DIR))
    searchoption.add_argument('--user-data-dir='+thread_USER_DATA_DIR)
    searchoption.add_experimental_option("excludeSwitches", ["enable-logging"])
    #searchoption.add_argument("--headless")                               #设置无头模式(不显示浏览器)
    #searchoption.add_experimental_option("prefs", prefs)            #加载无图模式设置
    processDriver = webdriver.Chrome(chrome_options=searchoption)

    for i in range(blocksNum):
        if blocks[i]['dealed'] == False:
            blocks[i]['dealed'] = True
            searchstr_block = searchstr
            if i > 0:
                waittime = 100
                preIndex = i
                while (preIndex > 0 and blocks[preIndex]['earliest_scan_time'] == ''):
                    waittime = 100
                    preIndex -= 1
                    while (blocks[preIndex]['earliest_scan_time'] == '' and waittime>0 ):    #wait other process change the value
                        sleep(2)
                        waittime -= 2
                searchstr_block += "+before:'{0}'".format(blocks[preIndex]['earliest_scan_time'])
            print("thread:{0}  searching:block{1}".format(threadID, i))
            res = searchOneBlock(searchstr_block, processDriver, i, blocks[i]['pages'])                
            if (res == -1):
                processDriver.quit()
                return -1
            with open("res.txt",'a') as f:
                e = time.time()
                f.write("********** milestone record **********\n")
                f.write("<{0}>block{3} done!  count:{1}  hasrun:{2}s".format(searchstr.strip(),datacount,time.time()-starttime,i))
            print("********** milestone record **********\n")
            print("<{0}>block{3} done!  count:{1}  hasrun:{2}s".format(searchstr.strip(),datacount,time.time()-starttime,i))
    processDriver.quit()

class myThread(Thread):
    def __init__(self,threadID,searchstr:str):
        Thread.__init__((self))
        self.threadID = threadID
        self.searchstr = searchstr
    def run(self):
        sleep(random.randint(10,20))
        searchProcess(self.searchstr, self.threadID)


def getTotaltips(searchurl):
    global myDriver
    try :
        myDriver.get(searchurl)
        webdriverwait = WebDriverWait(myDriver, 60)

        totaltips =  webdriverwait.until(EC.presence_of_element_located((By.CSS_SELECTOR,'p.search-result-summary'))).text
        totaltips = re.findall(r'[About找到约] ([\d,]+)',totaltips)[0]
        myDriver.quit()
        return totaltips
    except Exception as e:
        sleep(10)
        return getTotaltips(searchurl)

def assignProcess(searchstr : str):
    global blocks
    global blocksNum
    global PROCESSES_NUM
    suffix = "&page={0}&pageSize=20"    #pageSize=50 no use
    prefix = 'https://www.zoomeye.org/searchResult?q='+urllib.parse.quote(searchstr)
    searchurl = prefix + suffix.format(1)
    totaltips = getTotaltips(searchurl)  
    totalnum = int(totaltips.replace(',',''))
    print("total data num:%d"%totalnum)
    print("preparing for threads...")
    blocksNum = (totalnum-1) // VIEWNUM +1
    for i in range(blocksNum):
        blocks.append({'dealed':False, 'earliest_scan_time':"",'pages':VIEWNUM//20})                 #means these blocks haven't been deal
    blocks[blocksNum-1]['pages'] = (totalnum % VIEWNUM + 19) // 20
    PROCESSES_NUM = min(blocksNum, PROCESSES_NUM)   #processes num can not larger than blocksnum
    threadList = []
    for i in range(PROCESSES_NUM):
        threadList.append(myThread(i,searchstr))
        threadList[i].start()
    for i in range(PROCESSES_NUM):
        threadList[i].join()

    # clearfixs = webdriverwait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR,'div.clearfix')))
    # search_result_pagination_clearfix = webdriverwait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR,'div.clearfix')))[-1]
    # totalpage = int(search_result_pagination_clearfix.find_elements_by_tag_name('li')[-3].text)
    # #resdiv = webdriverwait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR,'div.search-result-item clearfix')))
    # print(searchurl)
    # for curpage in range(totalpage,0,-1):
    #     getOnePageInfo(prefix + suffix.format(curpage),curpage)

def main():
    global MONGO_TABLE
    global datacount
    global starttime
    global USERNAME
    global PASSWORD

    with open("password.txt","r") as f:
        USERNAME = f.readline()
        PASSWORD = f.readline()

    login('https://sso.telnet404.com/cas/login?service=https://www.zoomeye.org/login')

    with open("searchStr.txt",mode='r') as f:
        SEARCHSTRS = f.readlines()
    for orisearchstr in SEARCHSTRS:
        MONGO_TABLE = orisearchstr.replace(" ","_").replace("\"","").strip().split(",")[-1]
        datacount = 0
        searchstr = orisearchstr.strip().split(",")[0]
        assignProcess(searchstr)
        e = time.time()
        with open("res.txt",'a') as f:
            f.write("**********summary**********\n")
            f.write("<{0}>  count:{1}  time:{2}s\n".format(searchstr.strip(),datacount,e-starttime))
        print("<{0}>  count:{1}  time:{2}s".format(searchstr.strip(),datacount,e-starttime))
    print("ok")

if __name__ == '__main__':
    if len(sys.argv) == 2:
        try:
           print("process num:{}".format(sys.argv[1]))
           PROCESSES_NUM = int(sys.argv[1])
        except Exception:
            print("input err")
            myDriver.quit()
            exit(0)
    global starttime
    starttime = time.time()
    main()
    e = time.time()
    print("@@@@total_time:{0}s".format(e-starttime))
    #proxy.close()
