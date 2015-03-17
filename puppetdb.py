#!/usr/bin/env python
#
#   Copyright (c) 2015 iWeb Technologies Inc.
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
#   Author: David Moreau Simard <dmsimard@iweb.com>
#
from __future__ import print_function
import argparse
import collections
import os
import sys
import time
import yaml
from pypuppetdb import connect

try:
    import json
except ImportError:
    import simplejson as json


# First file found will have precedence
CONFIG_FILES = [
    os.path.expanduser(os.environ.get('ANSIBLE_PUPPETDB_CONFIG',
                                      "~/puppetdb.yml")),
    os.getcwd() + '/puppetdb.yml',
    '/etc/ansible/puppetdb.yml'
]


def load_config():
    """
    Looks for and loads yml configuration files
    """
    for path in CONFIG_FILES:
        if os.path.exists(path):
            try:
                with open(path) as config_file:
                    config = yaml.safe_load(config_file.read())
                    return config
            except IOError as error:
                print("I/O error ({0}): {1}".format(path, error.strerror))
                sys.exit(1)

    return None


class PuppetdbInventory(object):
    """
    A class that wraps around pypuppetdb to return ansible-compatible host
    lists and their hostvars (facts) based on data provided by PuppetDB.
    """
    def __init__(self, refresh):
        self.config = load_config()
        if not self.config:
            sys.exit('Error: Could not load any config files: {0}'
                     .format(', '.join(CONFIG_FILES)))

        puppetdb_config = {
            'host': self.config.get('host'),
            'api_version': self.config.get('api_version'),
            'port': self.config.get('port'),
            'timeout': self.config.get('timeout'),
            'ssl_verify': self.config.get('ssl_verify'),
            'ssl_key': self.config.get('ssl_key') or None,
            'ssl_cert': self.config.get('ssl_cert') or None
        }

        self.puppetdb = connect(**puppetdb_config)

        self.cache_file = self.config.get('cache_file')
        self.cache_duration = self.config.get('cache_duration')
        self.refresh = refresh

    def is_cache_stale(self):
        """
        Validates whether or not the cache file is stale
        """
        if os.path.isfile(self.cache_file):
            mod_time = os.path.getmtime(self.cache_file)
            current_time = time.time()
            if (mod_time + self.cache_duration) > current_time:
                return False

        return True

    def write_cache(self, groups):
        """
        Writes to the cache file
        """
        with open(self.cache_file, 'w') as cache_file:
            cache_file.write(groups)

    def get_host_list(self):
        """
        Updates the cache file, if necessary, and returns the inventory from it
        """
        if self.is_cache_stale() or self.refresh:
            groups = self.fetch_host_list()
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

    def fetch_host_list(self):
        """
        Returns data for all hosts found in PuppetDB
        """
        groups = collections.defaultdict(dict)
        hostvars = collections.defaultdict(dict)

        groups['all']['hosts'] = list()

        group_by = self.config.get('group_by')

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
                    if 'unknown' not in groups:
                        groups['unknown']['hosts'] = list()
                    groups['unknown']['hosts'].append(server)

            groups['all']['hosts'].append(server)
            hostvars[server] = self.fetch_host_facts(server)
            groups['_meta'] = {'hostvars': hostvars}

        return json.dumps(groups, sort_keys=True, indent=2)


def parse_args():
    """
    Parses script arguments.
    """
    parser = argparse.ArgumentParser(description='PuppetDB Inventory Module')
    parser.add_argument('--refresh', action='store_true', default=False,
                        help='Refreshes cached information')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true',
                       help='List servers known by PuppetDB')
    group.add_argument('--host',
                       help='List details about specified host')
    return parser.parse_args()


def main():
    """
    Instanciate the inventory and return a single host or a list of hosts
    """
    args = parse_args()

    inventory = PuppetdbInventory(args.refresh)
    if args.list:
        print(inventory.get_host_list())

    if args.host:
        print(inventory.get_host_detail(args.host))

if __name__ == '__main__':
    main()
