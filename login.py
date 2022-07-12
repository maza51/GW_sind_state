#!/usr/bin/python
# -*- coding: utf-8 -*-

from grab import Grab
import re
import os
import time
import traceback
import mysql.connector

TBLDEF = """\
CREATE TABLE pers (
   msgID INTEGER AUTO_INCREMENT PRIMARY KEY,
   msgMessageID VARCHAR(128),
   msgDate DATETIME,
   msgRecipient VARCHAR(128),
   msgText LONGTEXT
)"""


class Login(object):

    def __init__(self, user='sind_state', passw='555555'):
        self.user = user
        self.passw = passw

    def call(self):
        g = Grab(cookiefile=os.path.join(os.path.dirname(__file__), 'cookies.txt'))
        try:
            g.go('http://www.ganjawars.ru/login.php')
            g.doc.set_input('login', self.user)
            g.doc.set_input('pass', self.passw)
            g.doc.submit()
        except Exception as err:
            print ("ERROR: {0}".format(traceback.format_exc()))
            return False
        result = re.finditer(
            ur'Ваш персонаж',
            g.doc.unicode_body(), re.IGNORECASE | re.MULTILINE | re.DOTALL)
        for match in result:
            return True


class Sindicat(object):

    def __init__(self, sind_id=1):
        self.sind_id = sind_id

    def get_persons(self):
        persons = []
        g = Grab(cookiefile=os.path.join(os.path.dirname(__file__), 'cookies.txt'))
        try:
            g.go('http://www.ganjawars.ru/syndicate.php?id={0}&page=members'.format(self.sind_id))
        except Exception as err:
            print ("ERROR: {0}".format(traceback.format_exc()))
            return None
        items = g.xpath_list('//table[@class="wb"]/tr/td/nobr/a/b')
        for i in items:
                persons.append(i.xpath('string()'))
        return persons

    def get_battles(self):
        battles = []
        st = 0
        while st < 5:
            g = Grab(cookiefile=os.path.join(os.path.dirname(__file__), 'cookies.txt'))
            try:
                g.go('http://www.ganjawars.ru/syndicate.log.php?id={0}&warstats=1&page_id={1}'.format(self.sind_id, st))
            except Exception as err:
                print ("ERROR: {0}".format(traceback.format_exc()))
                return None
            items = g.xpath_list('//div[@class="gw-container"]/nobr/a[contains(@href,"warlog.php?bid")]')
            for i in items:
                battles.append(i.xpath('substring-after(@href, "/warlog.php?bid=")'))
            st += 1
        return battles


class Battle(object):

    def __init__(self, bid=1):
        self.bid = bid
        self.persons = []
        self.time_start = None
        self.time_end = None
        self.html = None

    def _get_dc(self, pers):
        n = 0
        result = re.finditer(
            ur'<b>{0}</b> (пропускает) ход'.format(pers),
            self.html, re.UNICODE | re.IGNORECASE | re.MULTILINE | re.DOTALL)
        for match in result:
            n += 1
        return n

    def _is_attacker(self, pers):
        result = re.search(
            ur'начался бой <font color=red><!-- s\d+ -->{0}[^<]+<'.format(pers),
            self.html, re.UNICODE | re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if result:
            return 1
        return 0

    def _is_granade(self, pers):
        result = re.search(
            ur': <b>{0}</b> запустил осветительную|<b>{0}</b> закрывает свою команду'.format(pers),
            self.html, re.UNICODE | re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if result:
            return 1
        return 0

    def _is_zamena(self, pers):
        result = re.search(
            ur'<font color=#880000>{0} входит в бой.</font>'.format(pers),
            self.html, re.UNICODE | re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if result:
            return 1
        return 0

    def _parse_persons_winners(self):
        result = re.finditer(
            ur'<BR>(.{,20}) за нанесённые повреждения в (\d+) HP получает <font color=#006600>(\d+)</font> опыта [^,]+, ([^\s]*) владений ?и? ?(\d+)?',
            self.html, re.UNICODE | re.IGNORECASE | re.MULTILINE | re.DOTALL)
        for match in result:
            p = {
                'name': match.groups()[0],
                'opit': match.groups()[2],
                'umka': match.groups()[3],
                'sind_opit': match.groups()[4] if match.groups()[4] else 0,
                'dc': self._get_dc(match.groups()[0]),
                'zamena': self._is_zamena(match.groups()[0]),
                'granade': self._is_granade(match.groups()[0]),
                'attacker': self._is_attacker(match.groups()[0]),
                'won': 1
            }
            self.persons.append(p)

    def _parse_persons_lossers(self):
        search = re.search(
            ur'Владение оружием для проигравших: ([^<]+)</span>',
            self.html, re.UNICODE | re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if search:
            result = re.finditer(
                ur'([^:]{,20}): ([^\s]*) ?и? ?(\d+)?( синдопыта, )?',
                search.group(1), re.UNICODE | re.IGNORECASE | re.MULTILINE | re.DOTALL)
            for match in result:
                p = {
                    'name': match.groups()[0],
                    'opit': 0,
                    'umka': match.groups()[1],
                    'sind_opit': match.groups()[2] if match.groups()[2] else 0,
                    'dc': self._get_dc(match.groups()[0]),
                    'zamena': self._is_zamena(match.groups()[0]),
                    'granade': self._is_granade(match.groups()[0]),
                    'attacker': self._is_attacker(match.groups()[0]),
                    'won': 0
                }
                self.persons.append(p)

    def _parse_time(self):
        result = re.finditer(
            ur'>Бой окончен ([^<]+)</font>',
            self.html, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        for match in result:
            self.time_end = match.groups()[0]
        result = re.finditer(
            ur'<span class=txt>(.+) начался бой',
            self.html, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        for match in result:
            self.time_start = match.groups()[0]
        if self.time_start and self.time_end:
            return True
        return False

    def parse(self):
        g = Grab(cookiefile=os.path.join(os.path.dirname(__file__), 'cookies.txt'))
        try:
            g.go('http://www.ganjawars.ru/warlog.php?bid={0}'.format(self.bid))
        except Exception as err:
            print ("ERROR: {0}".format(traceback.format_exc()))
            return False
        self.html = g.doc.unicode_body()
        return True

    def save(self):
        pass


if __name__ == '__main__':
    #print Login('sind_state', '555555').call()
    s = Sindicat(5300)
    #s.get_battles()
    b = Battle(1273501017)
    db = mysql.connector.connect(host='localhost', database='5300', user='root', password='194352')
    cursor = db.cursor()
    cursor.execute('CREATE TABLE `classdescription` (`ClassID` mediumint(9) NOT NULL auto_increment,`ClassType` varchar(10) NOT NULL default '',`ClassName` varchar(50) NOT NULL default '',`ClassDate` datetime NOT NULL default '0000-00-00 00:00:00',`ClassMax` mediumint(9) default NULL,PRIMARY KEY (`ClassID`)) ENGINE=MyISAM DEFAULT CHARSET=latin1 AUTO_INCREMENT=1 ;')
    cursor.close()
    db.close()
    #b.parse()
    #print b.persons
    #if b.parse():
        #print b.html
