#!/usr/bin/env python

import sys
import utils
from himlarcli.nova import Nova
from himlarcli.keystone import Keystone
from himlarcli.ldapclient import LdapClient

options = utils.get_options('Print openstack user stats', hosts=False)
keystoneclient = Keystone(options.config, options.debug)
projects = keystoneclient.list_projects('dataporten')
logger = keystoneclient.get_logger()

count = dict()
count['type'] = { 'staff': 0, 'student': 0, 'faculty': 0 }

conf = dict()
conf['uib'] = {
    'server': 'ldap.uib.no',
    'base_dn': 'dc=uib,dc=no',
    'type': 'employeeType',
    'org': 'ou'
}
conf['uio'] = {
    'server': 'ldap.uio.no',
    'base_dn': 'dc=uio,dc=no',
    'type': 'eduPersonPrimaryAffiliation',
    'org': 'eduPersonPrimaryOrgUnitDN'
}

uib = LdapClient(options.config, conf['uib'], options.debug, logger)
uio = LdapClient(options.config, conf['uio'], options.debug, logger)

# Generate attr list for each location
for i in conf.keys():
    conf[i]['attr'] = [conf[i]['type'], conf[i]['org']]

for mail in projects:
    print "---------------- %s ------------------" % mail
    if 'uib' in mail:
        # student
        if 'student' in mail:
            count['type']['student'] += 1
        else:
            user = uib.get_user(mail, attr=conf['uib']['attr'])[0]
            if 'IT-avdelingen' or 'Kommunikasjonsavdelingen' in user[1][conf['uib']['org']]:
                count['type']['staff'] += 1
            else:
                print user[1]
    elif 'uio' in mail:
        user = uio.get_user(mail, attr=conf['uio']['attr'])[0]
        print user[1][conf['uio']['type']][0]
        print user[conf['uio']['type']]
        #print uio.get_user(mail, attr=conf['uio']['attr'])

print count
