from himlarcli.client import Client
from neutronclient.v2_0.client import Client as neutronclient
from neutronclient.common import exceptions
import ipaddress

class Neutron(Client):

    """ Constant used to mark a class as region aware """
    USE_REGION = True

    def __init__(self, config_path, debug=False, log=None, region=None):
        super(Neutron, self).__init__(config_path, debug, log, region)
        self.logger.debug('=> init neutron client for region %s' % self.region)
        self.client = neutronclient(session=self.sess,
                                    region_name=self.region)

    def get_client(self):
        return self.client

# ================================== SEC GROUP ===============================

    def create_security_group(self, name, description='Generated by himlarcli'):
        secgroup = self.client.create_security_group(body={
            'security_group':
            {
                'name': name,
                'description': description
            }
        })
        return secgroup

    def create_security_group_rule(self, secgroup_id, port, protocol='tcp', ethertype='IPv4'):
        self.logger.debug('=> create security rule for port %s (%s, %s)',
                          port, protocol, ethertype)
        self.client.create_security_group_rule(body={
            'security_group_rule':
            {
                'security_group_id': secgroup_id,
                'direction': 'ingress',
                'protocol': protocol,
                'port_range_min': port,
                'port_range_max': port,
                'ethertype': ethertype
            }
        })

    def delete_security_group(self, secgroup_id):
        self.debug_log('delete secgroup %s' % secgroup_id)
        try:
            self.client.delete_security_group(secgroup_id)
        except (exceptions.NotFound, exceptions.Conflict) as e:
            self.log_error(e)

    def create_security_port_group(self, name, port, ipv6=True):
        secgroup = self.create_security_group(name)
        self.create_security_group_rule(secgroup['security_group']['id'], port)
        if ipv6:
            self.create_security_group_rule(secgroup_id=secgroup['security_group']['id'],
                                            port=port, ethertype='IPv6')
        return secgroup['security_group']

    def purge_security_groups(self, project):
        """ Remove all security groups for a project """
        try:
            sec_groups = self.client.list_security_groups(tenant_id=project.id)
        except exceptions.ServiceUnavailable:
            self.log_error('Neutron: Service Unavailable')
            sec_groups = None
        if not sec_groups:
            return
        for sg in sec_groups['security_groups']:
            self.delete_security_group(sg['id'])

# =================================== NETWORK ================================

    def list_networks(self, retrieve_all=True):
        network_list = list()
        networks = self.client.list_networks(retrieve_all=retrieve_all)
        if not networks:
            return list()
        for network in networks['networks']:
            network_list.append(network)
        return network_list

    def list_subnets(self, retrieve_all=True, **kwargs):
        try:
            subnets = self.client.list_subnets(retrieve_all=retrieve_all, **kwargs)
        except exceptions.ServiceUnavailable:
            self.log_error('Neutron: Service unavailable!')
        if 'subnets' not in subnets:
            return list()
        else:
            return subnets['subnets']

    def get_allocation_pool_size(self, network_id, ip_version=4):
        subnets = self.list_subnets(retrieve_all=True,
                                    network_id=network_id,
                                    ip_version=ip_version)
        pool_size = 0
        for subnet in subnets:
            start = ipaddress.ip_address(subnet['allocation_pools'][0]['start'])
            end = ipaddress.ip_address(subnet['allocation_pools'][0]['end'])
            pool_size += int(end) - int(start)
        return pool_size

# ==================================== QUOTA ==================================
    def get_quota_class(self, class_name='default'):
        """ Quota class are not used by neutron. This function only follow the
            structure in functions for nova and cinder. """
        self.log_error('quota_class not defined for neutron', 0)
        return dict()

    def update_quota_class(self, class_name='default', updates=None):
        """ Quota class are not used by neutron. This function only follow the
            structure in functions for nova and cinder. """
        self.log_error('quota_class not defined for neutron', 0)
        return dict()

    def get_quota(self, project_id, usage=False):
        result = self.client.show_quota(project_id=project_id)
        if 'quota' in result:
            return result['quota']
        return dict()

    def update_quota(self, project_id, updates):
        """ Update project neutron quota
            version: 2 """
        dry_run_txt = 'DRY-RUN: ' if self.dry_run else ''
        self.logger.debug('=> %supdate quota for %s = %s' % (dry_run_txt, project_id, updates))
        result = None
        try:
            if not self.dry_run:
                result = self.client.update_quota(project_id=project_id, body={'quota': updates})
        except exceptions.NotFound as e:
            self.log_error(e)
        except exceptions.ServiceUnavailable:
            self.log_error('Neutron: Service unavailable!')
        return result
