#!/usr/bin/env python
#   Copyright (c) 2015 David Moreau Simard <moi@dmsimard.com>
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

import argparse
import collections
import os
import time
from pypuppetdb import connect

try:
    import json
except:
    import simplejson as json


class PuppetdbInventory(object):
    def __init__(self, **kwargs):
        # Args we don't want to pass to PyPuppetDB
        del kwargs['list']
        del kwargs['server']
        del kwargs['group_by']

        self.puppetdb = connect(**kwargs)

        self.cache_file = os.path.join('/tmp/', "ansible-puppetdb.cache")
        self.cache_max_age = 60

    def is_cache_stale(self):
        """
        Validates whether or not the cache file is stale
        """
        if os.path.isfile(self.cache_file):
            mod_time = os.path.getmtime(self.cache_file)
            current_time = time.time()
            if (mod_time + self.cache_max_age) > current_time:
                return False

        return True

    def write_cache(self, groups):
        """
        Writes to the cache file
        """
        with open(self.cache_file, 'w') as cache_file:
            cache_file.write(groups)

    def get_host_list(self, group_by):
        """
        Updates the cache file, if necessary, and returns the inventory from it
        """
        if self.is_cache_stale():
            groups = self.fetch_host_list(group_by)
            self.write_cache(groups)

        groups = json.load(open(self.cache_file, 'r'))
        return json.dumps(groups, sort_keys=True, indent=2)

    def get_host_detail(self, host):
        """
        Returns data for a specific host only
        """
        facts = {
            host: self.fetch_host_facts(host)
        }

        return json.dumps(facts, sort_keys=True, indent=2)

    def fetch_host_facts(self, host):
        """
        Fetch all fact and their values for a given host
        """
        node = self.puppetdb.node(host)
        facts = {
            fact.name: fact.value
            for fact in node.facts()
        }

        facts['ansible_ssh_host'] = node.fact('fqdn').value

        return facts

    def fetch_host_list(self, group_by):
        """
        Returns data for all hosts found in PuppetDB
        """
        groups = collections.defaultdict(dict)
        hostvars = collections.defaultdict(dict)

        groups['unknown']['hosts'] = list()
        groups['all']['hosts'] = list()

        for node in self.puppetdb.nodes():
            server = str(node)

            if group_by is not None:
                try:
                    fact_value = node.fact(group_by).value
                    if fact_value not in groups:
                        groups[fact_value]['hosts'] = list()
                    groups[fact_value]['hosts'].append(server)
                except StopIteration:
                    # This fact does not exist on the server
                    groups['unknown']['hosts'].append(server)

            groups['all']['hosts'].append(server)
            hostvars[server] = self.fetch_host_facts(server)
            groups['_meta'] = {'hostvars': hostvars}

        return json.dumps(groups, sort_keys=True, indent=2)


def parse_args():
    """
    Parses script arguments.
    Note: Pypuppetdb expects a parameter 'host' for the host on which it
    will connect to PuppetDB.
    Since this conflicts with the expected '--host' expected parameter for
    the ansible inventory, they are interchanged here.
    """
    parser = argparse.ArgumentParser(description='PuppetDB Inventory Module')
    parser.add_argument('--server', default='localhost', dest='host',
                        help='PuppetDB server. Defaults to localhost.')
    parser.add_argument('--ssl_verify', default=False, action='store_true',
                        help='Verify SSL certificate. Defaults to False.')
    parser.add_argument('--ssl_key', default=None,
                        help='Path to SSL client key. Defaults to None.')
    parser.add_argument('--ssl_cert', default=None,
                        help='Path to SSL client cert. Defaults to None.')
    parser.add_argument('--api_version', type=int, default=3,
                        help='API Version for puppetdb. Defaults to 3')
    parser.add_argument('--port', type=int, default=8080,
                        help='PuppetDB port. Defaults to 8080.')
    parser.add_argument('--timeout', type=int, default=10,
                        help='Max timeout in seconds. Defaults to 10.')
    parser.add_argument('--group_by', default='node_role',
                        help='Fact with which the groups will be made.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true',
                       help='List servers known by PuppetDB')
    group.add_argument('--host', dest='server',
                       help='List details about specified host')
    return parser.parse_args()


def main():
    args = parse_args()

    inventory = PuppetdbInventory(**vars(args))
    if args.list:
        print(inventory.get_host_list(args.group_by))

    if args.server:
        print(inventory.get_host_detail(args.server))

if __name__ == '__main__':
    main()
