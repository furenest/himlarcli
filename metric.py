#!/usr/bin/env python

from himlarcli import tests as tests
tests.is_virtual_env()

from himlarcli.keystone import Keystone
from himlarcli.nova import Nova
from himlarcli.gnocchi import Gnocchi
from himlarcli.parser import Parser
from himlarcli.printer import Printer
from himlarcli import utils as himutils
from datetime import date, timedelta
from collections import defaultdict

parser = Parser()
options = parser.parse_args()
printer = Printer(options.format)

kc = Keystone(options.config, debug=options.debug)
kc.set_dry_run(options.dry_run)
region = kc.get_region() # use default from config
logger = kc.get_logger()
nc = Nova(options.config, debug=options.debug, log=logger, region=region)
nc.set_dry_run(options.dry_run)

def action_identity():
    start = himutils.get_date(None, date.today() - timedelta(days=30))
    stop = himutils.get_date(None, date.today() + timedelta(days=1))
    gc = Gnocchi(options.config, debug=options.debug, log=logger, region=region)
    client = gc.get_client()
    resources = client.resource.list(resource_type='identity', details=True, history=True)
    printer.output_dict({'header': 'identiy events: %s (user, date, events)' % len(resources)})
    for resource in resources:
        output = {
            1: resource['user_id'],
            0: resource['started_at'],
            2: 0
        }
        for metric, metric_id in resource['metrics'].items():
            measurement = client.metric.get_measures(metric=metric_id,
                                                     aggregation='count',
                                                     start=start,
                                                     stop=stop,
                                                     refresh=True)
            if measurement:
                output[2] += measurement[0][2]
        printer.output_dict(output, one_line=True)

def action_resources():
    gc = Gnocchi(options.config, debug=options.debug, log=logger, region=region)
    client = gc.get_client()
    resources = gc.get_resource_types()
    for resource in resources:
        rlist = client.resource.list(resource_type=resource['name'], details=True)
        if rlist:
            printer.output_dict({'header': 'resource type: %s' % resource['name']})
            printer.output_msg('number of resources %s' % len(rlist))

def action_metrics():
    gc = Gnocchi(options.config, debug=options.debug, log=logger, region=region)
    client = gc.get_client()
    metrics = client.metric.list()

    # for metric in metrics:
    #     print('metric name: %s' % metric['name'])
    printer.output_msg('number of metrics %s' % len(metrics))


def action_instance():
    start = himutils.get_date(options.start, date.today() - timedelta(days=1))
    stop = himutils.get_date(options.end, date.today() + timedelta(days=1))
    gc = Gnocchi(options.config, debug=options.debug, log=logger, region=region)
    instance = nc.get_by_id('server', options.instance)
    resources = gc.get_resource(resource_type='instance', resource_id=instance.id)
    metrics = resources['metrics']
    del resources['metrics']
    printer.output_dict({'header': 'instance metadata'})
    printer.output_dict(resources)
    printer.output_dict({'header': 'instance metrics'})
    output = defaultdict(int)
    for k, v in metrics.items():
        measurement = gc.get_client().metric.get_measures(metric=v,
                                                          aggregation='max',
                                                          start=start,
                                                          stop=stop)
        if measurement:
            output[k] += measurement[0][2]
    printer.output_dict(output)

# Run local function with the same name as the action
action = locals().get('action_' + options.action)
if not action:
    himutils.sys_error("Function action_%s() not implemented" % options.action)
action()
