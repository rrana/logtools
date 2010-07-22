#!/usr/bin/env python
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License. 
"""Unit-test code for logtools"""

import os
import sys
import unittest
import logging
from tempfile import mkstemp
from datetime import datetime
from StringIO import StringIO
from operator import itemgetter

from logtools import (filterbots, geoip, logsample, logsample_weighted, 
                      logparse, logmerge, logplot)
from logtools.parsers import *
from logtools import logtools_config, interpolate_config, AttrDict

logging.basicConfig(level=logging.INFO)

class ConfigurationTestCase(unittest.TestCase):
    def testInterpolation(self):
        self.assertEqual(1, interpolate_config(1, 'bogus_sec', 'bogus_key'))
        self.assertRaises(KeyError, interpolate_config, None, 'bogus_sec', 'bogus_key')


class ParsingTestCase(unittest.TestCase):
    def setUp(self):
        self.clf_rows = [
            '127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326',
            '127.0.0.2 - jay [10/Oct/2000:13:56:12 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326'
            ]
        self.json_rows = [
            '{"key1":"val1","key2":true,"key3":31337,"key4":null,"nested_key":[{"nested_key_1":"2"}]}'
        ]
        
    def testJSONParser(self):
        parser = JSONParser()
        for logrow in self.json_rows:
            parsed = parser(logrow)
            self.assertNotEquals(parsed, None, "Could not parse line: %s" % str(logrow))
        
    def testAccessLog(self):
        parser = AccessLog()
        parser.set_format(format='%h %l %u %t "%r" %>s %b')
        self.assertRaises(ValueError, parser, 'example for invalid format')
        for logrow in self.clf_rows:
            parsed = parser(logrow)
            self.assertNotEquals(parsed, None, "Could not parse line: %s" % str(logrow))
            
    def testCommonLogFormat(self):
        parser = CommonLogFormat()
        self.assertRaises(ValueError, parser, 'example for invalid format')
        for logrow in self.clf_rows:
            parsed = parser(logrow)
            self.assertNotEquals(parsed, None, "Could not parse line: %s" % str(logrow))        
        
    def testLogParse(self):
        options = AttrDict({'parser': 'CommonLogFormat', 'field': 4})
        fh = StringIO('\n'.join(self.clf_rows))
        output = [l for l in logparse(options, None, fh)]
        self.assertEquals(len(output), len(self.clf_rows), "Output size was not equal to input size!")
        
    def testMultiKeyGetter(self):
        parser = parser = CommonLogFormat()
        func = multikey_getter_gen(parser, keys=(1,2), is_indices=True)
        fh = StringIO('\n'.join(self.clf_rows))
        output = [func(l) for l in fh]
        self.assertEquals(len(output), len(self.clf_rows), "Output size was not equal to input size!")   
        
            
class FilterBotsTestCase(unittest.TestCase):
    def setUp(self):
        self.options = AttrDict({
            "reverse": False,
            "printlines": False,
            "ip_ua_re": "^(?P<ip>.*?) - USER_AGENT:'(?P<ua>.*?)'",
            "bots_ips": StringIO(),
            "bots_ua": StringIO("\n".join([
                "## Example comment ##",
                "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "ssearch_bot/Nutch-1.0 (sSearch Crawler; http://www.semantissimo.de)",
                "r'.*crawler'",
                "s'MSIECrawler)'",
                "p'DotSpotsBot'",
                "p'Java/'"
                ]) + "\n")
        })
        self.fh = StringIO(
            "127.0.0.1 - USER_AGENT:'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)' - ...\n" \
            "255.255.255.255 - USER_AGENT:'Mozilla' - ...\n" \
            "1.1.1.1 - USER_AGENT:'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; MSIECrawler)'\n" \
            "2.2.2.2 - USER_AGENT:'Mozilla/4.0 (compatible; MSIE 6.0; Windows 98; Win 9x 4.90; .NET CLR 1.1.4322; MSIECrawler)'\n" \
            "3.3.3.3 - USER_AGENT:'DotSpotsBot/0.2 (crawler; support at dotspots.com)'\n" \
            "4.4.4.4 - USER_AGENT:'inagist.com url crawler'\n" \
            "5.5.5.5 - USER_AGENT:'Java/1.6.0_18'\n" \
            "6.6.6.6 - USER_AGENT:'ssearch_bot/Nutch-1.0 (sSearch Crawler; http://www.semantissimo.de)'\n"
        )

    def testFiltering(self):
        i=0
        for l in filterbots(fh=self.fh, **self.options): 
            i+=1
        self.assertEquals(i, 1, "filterbots output size different than expected: %s" % str(i))


class GeoIPTestCase(unittest.TestCase):
    def setUp(self):
        self.options = AttrDict({ 'ip_re': '^(.*?) -' })
        
        self.fh = StringIO(
            "127.0.0.1 - USER_AGENT:'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)' - ...\n" \
            "255.255.255.255 - USER_AGENT:'Mozilla' - ...\n"
        )

    def testGeoIP(self):
        try:
            import GeoIP
        except ImportError:
            print >> sys.stderr, "GeoIP Python package not available - skipping geoip unittest."
            return

        output = [(geocode, ip, line) for geocode, ip, line in geoip(fh=self.fh, **self.options)]
        self.assertEquals(len(output), 2, "Output size was different than expected: %s" % str(len(output)))

        
class SamplingTestCase(unittest.TestCase):
    def setUp(self):
        self.options = AttrDict({ 'num_samples': 1 })
        self.weighted_opts = AttrDict({
            'num_samples': 5,
            'field': 1,
            'delimiter': ' '
        })
        self.fh = StringIO("\n".join([
            '5 five', '1 one', '300 threehundred', '500 fivehundred',
            '0 zero', '-1 minusone', '670 sixhundredseventy', '1000 thousand',
            '22 twentytwo', '80 eighty', '3 three'
        ]))

    def testUniformSampling(self):
        output = [r for r in logsample(fh=self.fh, **self.options)]
        self.assertEquals(len(output), self.options.num_samples, 
                          "logsample output size different than expected: %s" % len(output))
        
    def testWeightedSampling(self):
        output = [(k, r) for k, r in logsample_weighted(fh=self.fh, **self.weighted_opts)]
        self.assertEquals(len(output), self.weighted_opts.num_samples, 
                          "logsample output size different than expected: %s" % len(output))        

class MergeTestCase(unittest.TestCase):
    def setUp(self):
        self.tempfiles = [mkstemp(), mkstemp(), mkstemp()]
        self.args = [fname for fh, fname in self.tempfiles]

    def tearDown(self):
        """Cleanup temporary files created by test"""
        for fh, fname in self.tempfiles:
            os.remove(fname)
            
    def testNumericMerge(self):
        os.write(self.tempfiles[0][0], "\n".join(['1 one', '5 five', '300 threehundred', 
                                            '500 fivehundred']))
        os.write(self.tempfiles[1][0], "\n".join(['-1 minusone', '0 zero',
                                            '670 sixhundredseventy' ,'1000 thousand']))
        os.write(self.tempfiles[2][0], "\n".join(['3 three', '22 twentytwo', '80 eighty']))
        
        options = AttrDict({'delimiter': ' ', 'field': 1, 'numeric': True })
        output = [(k, l) for k, l in logmerge(options, self.args)]
        
        self.assertEquals(len(output), 11, "Output size was not equal to input size!")
        self.assertEquals(map(itemgetter(0), output), sorted(map(lambda x: int(x[0]), output)), 
                          "Output was not numerically sorted!")
        
    def testDateMerge(self):
        os.write(self.tempfiles[0][0], "\n".join(['2010/01/12 07:00:00,one', '2010/01/12 08:00:00,five', 
                                                  '2010/01/13 10:00:00,threehundred']))
        os.write(self.tempfiles[1][0], "\n".join(['2010/01/12 07:30:00,one', '2010/01/12 08:10:00,five', 
                                                  '2010/01/12 21:00:00,threehundred']))
        os.write(self.tempfiles[2][0], "\n".join(['2010/01/11 05:33:03,one', '2010/01/12 03:10:00,five', 
                                                  '2010/01/21 22:00:00,threehundred']))
        
        dateformat = '%Y/%m/%d %H:%M:%S'
        options = AttrDict({'delimiter': ',', 'field': 1, 'datetime': True, 'dateformat': dateformat })
        output = [(k, l) for k, l in logmerge(options, self.args)]
        
        self.assertEquals(len(output), 9, "Output size was not equal to input size!")
        self.assertEquals(map(itemgetter(0), output), sorted(map(itemgetter(0), output)), 
                          "Output was not time sorted!")        
        
    def testLexicalMerge(self):
        os.write(self.tempfiles[0][0], "\n".join(['1 one', '300 threehundred', '5 five', 
                                            '500 fivehundred']))
        os.write(self.tempfiles[1][0], "\n".join(['-1 minusone', '0 zero', '1000 thousand',
                                            '670 sixhundredseventy']))
        os.write(self.tempfiles[2][0], "\n".join(['22 twentytwo', '3 three', 
                                            '80 eighty']))
        
        options = AttrDict({ 'delimiter': ' ', 'field': 1, 'numeric': False })
        output = [(k, l) for k, l in logmerge(options, self.args)]
        
        self.assertEquals(len(output), 11, "Output size was not equal to input size!")
        self.assertEquals(map(itemgetter(0), output), sorted(map(itemgetter(0), output)), 
                          "Output was not lexically sorted!")
        
        
class PlotTestCase(unittest.TestCase):
    def setUp(self):
        self.fh = StringIO("\n".join([
            '5 five', '1 one', '300 threehundred', '500 fivehundred',
            '0 zero', '-1 minusone', '670 sixhundredseventy', '1000 thousand',
            '22 twentytwo', '80 eighty', '3 three'
        ]))

    def testGChart(self):
        try:
            import pygooglechart
        except ImportError:
            print >> sys.stderr, "pygooglechart Python package not available - skipping logplot gchart unittest."
            return        
        options = AttrDict({
            'backend': 'gchart',
            'output': False,
            'limit': 10,
            'field': 1,
            'delimiter': ' ',
            'legend': True,
            'width': 600,
            'height': 300
        })        
        chart = None
        for plot_type in ('pie', 'line'):
            self.fh.seek(0)
            options['type'] = plot_type
            chart = logplot(options, None, self.fh)
            self.assertNotEquals(chart, None, "logplot returned None. Expected a Plot object")
            
        # Should raise ValueError here due to fh being at EOF
        self.assertRaises(ValueError, logplot, options, None, self.fh)
        
        tmp_fh, tmp_fname = mkstemp()
        chart.download(tmp_fname)
        os.remove(tmp_fname)
    

if __name__ == "__main__":
    unittest.main()
