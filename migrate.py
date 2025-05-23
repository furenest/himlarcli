#!/usr/bin/env python

import time
import sys
import re
from datetime import timedelta
#from datetime import datetime
#from zoneinfo import ZoneInfo

from himlarcli import tests
tests.is_virtual_env()

from himlarcli.keystone import Keystone
from himlarcli.nova import Nova
from himlarcli.parser import Parser
from himlarcli.printer import Printer
from himlarcli import utils as himutils
from himlarcli.color import Color

parser = Parser()
options = parser.parse_args()
printer = Printer(options.format)

kc = Keystone(options.config, debug=options.debug)
kc.set_dry_run(options.dry_run)
logger = kc.get_logger()
nc = Nova(options.config, debug=options.debug, log=logger)
nc.set_dry_run(options.dry_run)

if hasattr(options, 'source'):
    source = nc.get_fqdn(options.source)
    search_opts = dict(all_tenants=1, host=source)
    if not nc.get_host(source):
        himutils.fatal(f"Could not find source host '{source}'")

#def action_show():
#    migrations = nc.get_migrations_by_instance_id(options.instance)
#    for m in migrations:
#        show_migration(m)
#
#
#def action_abort():
#    migrations = nc.get_migrations_by_instance_id(options.instance)
#    if len(migrations) == 0:
#        himutils.warning(f'No live-migrations found for instance {options.instance}, nothing to do')
#        return
#    if len(migrations) > 1:
#        himutils.error(f'More than 1 active live-migrations found for instance {options.instance}. Cannot continue')
#        return
#
#    # Show the migration to be aborted
#    show_migration(migrations[0])
#
#    # Get confirmation
#    q = f'Abort this migration'
#    if not himutils.confirm_action(q):
#        return
#
#    # Abort migration
#    nc.abort_live_migration(options.instance, migrations[0].id)
#
#
#def action_force_complete():
#    migrations = nc.get_migrations_by_instance_id(options.instance)
#    if len(migrations) == 0:
#        himutils.warning(f'No live-migrations found for instance {options.instance}, nothing to do')
#        return
#    if len(migrations) > 1:
#        himutils.error(f'More than 1 active live-migrations found for instance {options.instance}. Cannot continue')
#        return
#
#    # Show the migration to be aborted
#    show_migration(migrations[0])
#
#    # Get confirmation
#    q = f'Abort this migration'
#    if not himutils.confirm_action(q):
#        return
#
#    # Check if force-complete is possible
#    if migrations[0].status == "preparing":
#        himutils.error(f'Migration {migrations[0].id} state of instance {options.instance} is preparing.'
#                       f' Cannot force complete while the migration is in this state')
#        return
#
#    # Force-complete migration
#    nc.force_complete_live_migration(options.instance, migrations[0].id)


def action_list():
    instances = nc.get_all_instances(search_opts=search_opts)

    if options.format == 'table':
        output = {}
        output['header'] = [
            'ID',
            'NAME',
            'VM_STATE',
            'TASK_STATE',
        ]
        output['align'] = [
            'l',
            'l',
            'l',
            'l',
        ]
        output['sortby'] = 2
        output['reversesort'] = True
        counter = 0

        for i in instances:
            state = getattr(i, 'OS-EXT-STS:vm_state')
            state_task = getattr(i, 'OS-EXT-STS:task_state')
            if state == 'active':
                state_color = Color.fg.GRN
            elif state == 'stopped':
                state_color = Color.fg.RED
            else:
                state_color = Color.fg.YLW
            if state_task is None:
                state_task_color = Color.dim
            else:
                state_task_color = Color.fg.red
            output[counter] = [
                Color.dim + i.id + Color.reset,
                Color.fg.ylw + i.name + Color.reset,
                state_color + str(getattr(i, 'OS-EXT-STS:vm_state')) + Color.reset,
                state_task_color + str(getattr(i, 'OS-EXT-STS:task_state')) + Color.reset,
            ]
            counter += 1
        printer.output_dict(output, sort=True, one_line=False)
    else:
        printer.output_dict({'header': 'Instance list (id, name, state, task)'})
        for i in instances:
            output = {
                'id':         i.id,
                'name':       i.name,
                'state':      getattr(i, 'OS-EXT-STS:vm_state'),
                'state_task': getattr(i, 'OS-EXT-STS:task_state'),
            }
            printer.output_dict(output, sort=True, one_line=True)


def action_instance():
    target = nc.get_fqdn(options.target)
    target_details = nc.get_host(target)
    if not target_details or target_details.status != 'enabled':
        himutils.fatal(f'Could not find enabled target host {options.target}')
    instance = nc.get_by_id('server', options.instance)

    # Get confirmation
    q = f'Try to migrate instance {options.instance} to {target}'
    if not himutils.confirm_action(q):
        return

    # Migrate instance
    migrate_instance(instance, target)


def action_migrate():
    target = nc.get_fqdn(options.target)
    target_details = nc.get_host(target)
    if not target_details or target_details.status != 'enabled':
        himutils.fatal(f'Could not find enabled target host {options.target}')
    if options.limit:
        q = f'Try to migrate {options.limit} instance(s) from {source} to {target}'
    else:
        q = f'Migrate ALL instances from {source} to {target}'
    if not himutils.confirm_action(q):
        return
    # Disable source host unless no-disable param is used
    if not options.dry_run and not options.no_disable:
        nc.disable_host(source)
    instances = nc.get_all_instances(search_opts=search_opts)
    count = 0
    for i in instances:
        if options.stopped and getattr(i, 'OS-EXT-STS:vm_state') != 'stopped':
            kc.debug_log(f'drop migrate:  instance not stopped {i.name}')
            continue # do not count this instance for limit
        if options.large:
            if i.flavor['ram'] > options.filter_ram:
                migrate_instance(i, target)
            else:
                kc.debug_log('drop migrate instance %s: ram %s <= %s'
                             % (i.name, i.flavor['ram'], options.filter_ram))
                continue # do not count this instance for limit
        elif options.small:
            if i.flavor['ram'] < options.filter_ram:
                migrate_instance(i, target)
            else:
                kc.debug_log('drop migrate instance %s: ram %s >= %s'
                             % (i.name, i.flavor['ram'], options.filter_ram))
                continue # do not count this instance for limit
        else:
            migrate_instance(i, target)
        count += 1
        if options.limit and count >= options.limit:
            kc.debug_log('number of instances reached limit %s' % options.limit)
            break


def action_drain():
    if options.limit:
        q = f'Try to migrate {options.limit} instance(s) from {source} any target'
    else:
        q = f'Migrate ALL instances away from {source}'
    if not himutils.confirm_action(q):
        return
    # Disable source host unless no-disable param is used
    if not options.dry_run and not options.no_disable:
        nc.disable_host(source)
    instances = nc.get_all_instances(search_opts=search_opts)
    count = 0
    for i in instances:
        if options.stopped and getattr(i, 'OS-EXT-STS:vm_state') != 'stopped':
            kc.debug_log(f'drop migrate:  instance not stopped {i.name}')
            continue # do not count this instance for limit
        if options.large:
            if i.flavor['ram'] > options.filter_ram:
                migrate_instance(i)
            else:
                kc.debug_log('drop migrate instance %s: ram %s <= %s'
                             % (i.name, i.flavor['ram'], options.filter_ram))
                continue # do not count this instance for limit
        elif options.small:
            if i.flavor['ram'] < options.filter_ram:
                migrate_instance(i)
            else:
                kc.debug_log('drop migrate instance %s: ram %s >= %s'
                             % (i.name, i.flavor['ram'], options.filter_ram))
                continue # do not count this instance for limit
        else:
            migrate_instance(i)
        count += 1
        if options.limit and count >= options.limit:
            kc.debug_log('number of instances reached limit %s' % options.limit)
            break

def action_evacuate():
    source_host = nc.get_host(source)
    if source_host.state != 'down':
        himutils.fatal('Evacuate failed. Source host need to be down! Use migrate')
    # Check that there are other valid hosts in the same aggregate
    hosts = nc.get_aggregate_hosts(options.aggregate)
    found_enabled = []
    for host in hosts:
        if host.hypervisor_hostname == source:
            continue
        if host.status == 'enabled' and host.state == 'up':
            found_enabled.append(host.hypervisor_hostname)
    if not found_enabled:
        himutils.sys_error(f'Evacuate failed. No valid host in aggregate {options.aggregate}')
    logger.debug('=> valid host found %s', ", ".join(found_enabled))
    # Interactive question
    q = f'Evacuate all instances from {source} to other hosts'
    if not himutils.confirm_action(q):
        return
    instances = nc.get_all_instances(search_opts=search_opts)
    dry_run_txt = 'DRY_RUN: ' if options.dry_run else ''
    count = 0
    for i in instances:
        state = getattr(i, 'OS-EXT-STS:vm_state')
        logger.debug(f'=> {dry_run_txt}evacuate {i.name}')
        if state == 'active' and not options.dry_run:
            i.evacuate()
            time.sleep(options.sleep)
        elif state == 'stopped' and not options.dry_run:
            i.evacuate()
            time.sleep(options.sleep)
        elif not options.dry_run:
            logger.debug(f'=> dropping evacuate of {i.name} unknown state {state}')
        count += 1
        if options.limit and count > options.limit:
            logger.debug(f'=> number of instances reached limit {options.limit}')
            break

def migrate_instance(instance, target=None):
    """
    This will do the migration of an instance
    Allowed state for migration:
        * active
        * paused
        * stopped
    """
    state = getattr(instance, 'OS-EXT-STS:vm_state')
    state_task = getattr(instance, 'OS-EXT-STS:task_state')

    # Drop migration if instance has any running task
    if state_task:
        kc.debug_log('instance running task %s, dropping migrate' % state_task)
        himutils.warning(f'Instance {instance.name} ({instance.id} ' +
                         f'is running task {state_task}. Migration dropped')
        return

    # Drop migration if instance is not in a supported vm state
    handled_states = ['active', 'paused', 'stopped']
    if state not in handled_states:
        himutils.warning(f'Not migrating instance {instance.name} ({instance.id}): '
                         f'Unhandled VM state {state}')
        kc.debug_log('dropping migrate of %s unknown state %s' % (instance.name, state))
        return

    # Print information about the migration about to happen
    kc.debug_log('migrate %s to %s' % (instance.name, target))
    if state == 'active':
        state_color = Color.fg.grn
    elif state == 'stopped':
        state_color = Color.fg.RED
    else:
        state_color = Color.fg.blu
    sys.stdout.write(f'Migrating: {Color.fg.ylw}{instance.name}{Color.reset} '
                     f'({Color.dim}{instance.id}{Color.reset}) '
                     f'[{state_color}{state}{Color.reset}] ')
    sys.stdout.flush()

    # If dry-run: print and return
    if options.dry_run:
        print(" DONE (dry-run)")
        return

    # Set source hypervisor
    if 'source' in globals():
        source_host = source
    else:
        source_host = getattr(instance, 'OS-EXT-SRV-ATTR:hypervisor_hostname')

    # Call migrate or live-migrate depending on vm state
    if (state == 'active' or state == 'paused'):
        instance.live_migrate() if target is None else instance.live_migrate(host=target)
    elif state == 'stopped':
        instance.migrate() if target is None else instance.migrate(host=target)

    # Time the migration and report outcome
    timeout = 86400  # time out migration loop after 24 hours
    start = time.perf_counter()
    while True:
        timeout += -1
        migrating_instance = nc.get_by_id('server', instance.id)
        hypervisor = getattr(migrating_instance, 'OS-EXT-SRV-ATTR:hypervisor_hostname')
        task_state = getattr(migrating_instance, 'OS-EXT-STS:task_state')
        if task_state is None and hypervisor != source_host:
            finish = time.perf_counter()
            td_str = str(timedelta(seconds=(finish - start)))
            x = td_str.split(':')
            if int(x[0]) > 0:
                elapsed_str = "%d hours %d minutes %.1f seconds" % (int(x[0]), int(x[1]), float(x[2]))
            elif int(x[0]) == 0 and int(x[1]) > 0:
                elapsed_str = "%d minutes %.1f seconds" % (int(x[1]), float(x[2]))
            else:
                elapsed_str = "%.1f seconds" % float(x[2])
            new_host = re.sub('\.mgmt\..+?\.uhdc\.no$', '', hypervisor)
            print(f'––> {Color.fg.cyn}{new_host}{Color.reset} '
                  f'{Color.fg.grn}{Color.bold}COMPLETE{Color.reset} in {elapsed_str}')
            break
        elif task_state is None and hypervisor == source_host:
            print(f'{Color.fg.red}{Color.bold}FAILED!{Color.reset}')
            break
        elif timeout == 0:
            print(f'{Color.fg.red}{Color.bold}TIMEOUT after 24 hours!{Color.reset}')
            break
        time.sleep(1)

    # Sleep the desired amount before returning
    if hasattr(options, 'sleep'):
        time.sleep(options.sleep)

#def show_migration(m):
#    created_at = datetime.fromisoformat(f'{m.created_at}+00.00').astimezone(ZoneInfo('Europe/Oslo')).strftime('%Y-%m-%d %H:%M:%S %Z')
#    updated_at = datetime.fromisoformat(f'{m.updated_at}+00.00').astimezone(ZoneInfo('Europe/Oslo')).strftime('%Y-%m-%d %H:%M:%S %Z')
#    print(
#        '\n'
#        f'  {Color.fg.cyn}Status{Color.reset} {Color.dim}......................{Color.reset} {Color.bold}{m.status}{Color.reset}\n'
#        f'  {Color.fg.CYN}ID{Color.reset} {Color.dim}..........................{Color.reset} {m.id}\n'
#        f'  {Color.fg.CYN}Created At{Color.reset} {Color.dim}..................{Color.reset} {created_at}\n'
#        f'  {Color.fg.CYN}Updated At{Color.reset} {Color.dim}..................{Color.reset} {updated_at}\n'
#        f'  {Color.fg.CYN}Source Compute{Color.reset} {Color.dim}..............{Color.reset} {m.source_compute}\n'
#        f'  {Color.fg.CYN}Dest Compute{Color.reset} {Color.dim}................{Color.reset} {m.dest_compute}\n'
#        f'  {Color.fg.YLW}Total Memory Bytes{Color.reset} {Color.dim}..........{Color.reset} {m.memory_total_bytes}\n'
#        f'  {Color.fg.YLW}Processed Memory Bytes{Color.reset} {Color.dim}......{Color.reset} {m.memory_processed_bytes}\n'
#        f'  {Color.fg.YLW}Remaining Memory Bytes{Color.reset} {Color.dim}......{Color.reset} {m.memory_remaining_bytes}\n'
#        f'  {Color.fg.MGN}Total Disk Bytes{Color.reset} {Color.dim}............{Color.reset} {m.disk_total_bytes}\n'
#        f'  {Color.fg.MGN}Processed Disk Bytes{Color.reset} {Color.dim}........{Color.reset} {m.disk_processed_bytes}\n'
#        f'  {Color.fg.MGN}Remaining Disk Bytes{Color.reset} {Color.dim}........{Color.reset} {m.disk_remaining_bytes}\n'
#    )


# Run local function with the same name as the action
action = locals().get('action_' + options.action)
if not action:
    himutils.fatal("Function action_%s() not implemented" % options.action)
action()
