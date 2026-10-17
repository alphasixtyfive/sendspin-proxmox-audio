"""Recovery decisions and failure boundaries; never access real audio or Proxmox."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('usb_recovery', ROOT / 'scripts/usb-recovery.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def config():
    return {'ctid': 321, 'user': 'sendspin-cli', 'uid': 999,
            'routing_file': '/etc/pipewire/pipewire.conf.d/60-zones.conf',
            'cards': [{'usb_port': '1-2.' + str(n), 'vendor': 'abcd', 'product': '1234',
                       'alsa_id': 'CARD_' + letter, 'node': 'card_' + letter.lower(),
                       'slots': ['dev' + str(2 * i), 'dev' + str(2 * i + 1)]}
                      for i, (n, letter) in enumerate([(1, 'A'), (2, 'B')])]}


def observed(a=3, b=4):
    return {'CARD_' + letter: {'number': n, 'usb_devnum': '10', 'card_instance': 100 + n,
                              'paths': ['/dev/snd/controlC' + str(n), '/dev/snd/pcmC' + str(n) + 'D0p']}
            for letter, n in [('A', a), ('B', b)] if n is not None}


def conf_for(o):
    c = config()
    return {'unprivileged': '1', 'onboot': '1', 'startup': 'order=30',
            **{s: r.device_value(p) for card in c['cards'] if card['alsa_id'] in o
               for s, p in zip(card['slots'], o[card['alsa_id']]['paths'])}}


def states(stopped=()):
    return {name: {'Id': name, 'ActiveState': 'inactive' if name in stopped else 'active',
                   'SubState': 'dead' if name in stopped else 'running'}
            for name in ['sendspin-zones.target', 'pipewire.service', 'wireplumber.service',
                         'sendspin-zone@one.service', 'sendspin-zone@two.service']}


ROUTING = '''context.modules = [
 { name = libpipewire-module-loopback args = {
 capture.props = { node.name = "one" }
 playback.props = { node.name = "playback.one" target.object = "card_a" audio.position = [ FL FR ] } } }
 { name = libpipewire-module-loopback args = {
 capture.props = { node.name = "two" }
 playback.props = { node.name = "playback.two" target.object = "card_b" audio.position = [ RL RR ] } } }
]'''
SAVED = '''state.CARD_A {
 control.1 { iface MIXER name 'PCM Playback Volume' value.0 17 value.1 21
 comment { access 'read write' type INTEGER count 2 } }
 control.2 { iface MIXER name 'PCM Playback Switch' index 1 value true
 comment { access 'read write' type BOOLEAN count 1 } }
 control.3 { iface CARD name 'Output Jack' value false comment { access read } }
}'''


class PureTests(unittest.TestCase):
    def test_same_permission_set_survives_card_order_swap(self):
        old = r.parse_grants(conf_for(observed()))
        self.assertEqual(r.desired_grants(config(), observed(4, 3), old), old)

    def test_new_numbers_generate_only_reviewed_slots(self):
        d = r.desired_grants(config(), observed(5, 6), r.parse_grants(conf_for(observed())))
        self.assertEqual(set(d), {'dev0', 'dev1', 'dev2', 'dev3'})
        self.assertEqual(d['dev0'], '/dev/snd/controlC5')
        self.assertEqual(d['dev3'], '/dev/snd/pcmC6D0p')

    def test_boot_absent_card_has_no_missing_path_grant(self):
        self.assertEqual(set(r.desired_grants(config(), observed(None, 4), {})), {'dev2', 'dev3'})
        self.assertEqual(r.desired_grants(config(), {}, {}), {})

    def test_broad_capture_and_wrong_permissions_rejected(self):
        for value in ['/dev/snd/pcmC3D0c,gid=29,uid=0,mode=0660',
                      '/dev/snd/pcmC3D1p,gid=29,uid=0,mode=0660',
                      '/dev/snd/controlC3,gid=0,uid=0,mode=0666']:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                r.parse_grants({'dev0': value})

    def test_duplicate_grants_rejected(self):
        with self.assertRaises(RuntimeError):
            r.parse_grants({'dev0': r.device_value('/dev/snd/controlC3'),
                            'dev1': r.device_value('/dev/snd/controlC3')})

    def test_duplicate_permission_option_rejected(self):
        with self.assertRaises(RuntimeError):
            r.parse_grants({'dev0': '/dev/snd/controlC3,gid=0,gid=29,uid=0,mode=0660'})

    def test_pending_CT_update_is_not_overwritten(self):
        with patch.object(r, 'run', side_effect=['unprivileged: 1\nmemory: 1024\n',
                                               'unprivileged: 1\nmemory: 2048\n']):
            with self.assertRaisesRegex(RuntimeError, 'pending changes'): r.config(config())

    def test_saved_state_owns_values_and_boolean_conversion(self):
        self.assertEqual(r.calibration(SAVED, 'CARD_A'),
                         [("iface=MIXER,name='PCM Playback Volume'", ['17', '21']),
                          ("iface=MIXER,name='PCM Playback Switch',index=1", ['on'])])

    def test_incomplete_or_duplicate_state_rejected(self):
        for text in [SAVED[:-1], 'a 1 a 2', '}']:
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                r.alsa_tree(text)

    def test_missing_saved_card_rejected(self):
        with self.assertRaises(RuntimeError):
            r.calibration(SAVED, 'CARD_B')

    def test_live_mixer_mismatch_rejected(self):
        with patch.object(r, 'run', return_value='  : values=99,99\n'), self.assertRaises(RuntimeError):
            r.verify_calibration('CARD_A', r.calibration(SAVED, 'CARD_A'))

    def test_routes_derive_stereo_targets_from_existing_file(self):
        self.assertEqual(r.routes(ROUTING), [('one', 'playback.one', 'card_a', ['FL', 'FR']),
                                           ('two', 'playback.two', 'card_b', ['RL', 'RR'])])

    def test_missing_routes_and_duplicate_sinks_rejected(self):
        for text in ['', ROUTING.replace('node.name = "two"', 'node.name = "one"')]:
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                r.routes(text)

    def test_config_identity_and_unknown_keys_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            c = config(); path.write_text(json.dumps(c))
            with patch.object(r, 'secure'):
                self.assertEqual(r.load_config(path), c)
                for key, value in [('ctid', '321'), ('user', 'root;anything'), ('uid', 0)]:
                    bad = {**c, key: value}; path.write_text(json.dumps(bad))
                    with self.assertRaises(RuntimeError): r.load_config(path)
                c['cards'][1]['usb_port'] = c['cards'][0]['usb_port']
                path.write_text(json.dumps(c))
                with self.assertRaises(RuntimeError): r.load_config(path)

    def test_udev_rule_only_queues_events_for_configured_ports(self):
        text = r.rules(config())
        self.assertEqual(text.count('RUN+="/usr/local/libexec/sendspin-usb-recovery event"'), 2)
        self.assertIn('KERNEL=="1-2.1|1-2.2"', text)
        self.assertIn('KERNELS=="1-2.1|1-2.2"', text)
        self.assertNotIn('pct ', text)
        self.assertNotIn('MODE=', text)

    def test_target_dependencies_own_configured_instances(self):
        with patch.object(r, 'user', return_value='pipewire.service sendspin-zone@one.service sendspin-zone@two.service\n') as command:
            self.assertEqual(r.target_rooms(config()), {'sendspin-zone@one.service', 'sendspin-zone@two.service'})
            self.assertIn('--property=Wants', command.call_args.args)

    def test_stream_status_requires_paired_connection(self):
        self.assertTrue(r.stream_idle('trust: paired\nstream: idle\nprivate: ignored\n'))
        self.assertFalse(r.stream_idle('trust: paired\nstream: receiving\n'))
        for text in ['trust: not connected\nstream: idle\n', 'trust: paired\n', 'stream: idle\n']:
            with self.subTest(text=text), self.assertRaises(RuntimeError): r.stream_idle(text)

    def test_idle_wait_requires_two_idle_samples(self):
        with patch.object(r, 'still_enabled'), patch.object(r, 'inventory', return_value=observed()), \
             patch.object(r, 'user', side_effect=['trust: paired\nstream: receiving\n',
                                                 'trust: paired\nstream: idle\n',
                                                 'trust: paired\nstream: idle\n']) as command, \
             patch.object(r.time, 'sleep'):
            r.wait_idle(config(), {'sendspin-zone@one.service'}, observed())
            self.assertEqual(command.call_count, 3)

    def test_idle_timeout_does_not_stop_any_player(self):
        with patch.object(r, 'user') as command, self.assertRaisesRegex(RuntimeError, 'deferred'):
            r.wait_idle(config(), {'sendspin-zone@one.service'}, observed(), timeout=0)
        command.assert_not_called()

    def test_idle_wait_treats_a_disconnected_client_as_not_ready(self):
        with patch.object(r, 'still_enabled'), patch.object(r, 'inventory', return_value=observed()), \
             patch.object(r, 'user', side_effect=['trust: not connected\nstream: idle\n',
                                                 'trust: paired\nstream: idle\n',
                                                 'trust: paired\nstream: idle\n']) as command, \
             patch.object(r.time, 'sleep'):
            r.wait_idle(config(), {'sendspin-zone@one.service'}, observed())
            self.assertEqual(command.call_count, 3)

    def test_backup_lock_is_waited_out_without_unlocking(self):
        with patch.object(r, 'still_enabled'), \
             patch.object(r, 'config', side_effect=[RuntimeError('CT has a Proxmox task lock'), {'unprivileged': '1'}]), \
             patch.object(r.time, 'sleep') as sleep:
            self.assertEqual(r.wait_config(config()), {'unprivileged': '1'})
            sleep.assert_called_once_with(1)

    def test_pending_maintenance_is_not_retried_as_a_backup_lock(self):
        with patch.object(r, 'still_enabled'), patch.object(r, 'config', side_effect=RuntimeError('CT has unapplied pending changes')), \
             patch.object(r.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'pending'): r.wait_config(config())
            sleep.assert_not_called()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.c = config(); self.o = observed(); self.conf = conf_for(self.o)
        self.calls = []
        self.patches = []
        def set_mock(name, **kwargs):
            p = patch.object(r, name, **kwargs); self.patches.append(p)
            return p.start()
        self.set_mock = set_mock
        set_mock('still_enabled')
        self.config = set_mock('config', return_value=self.conf)
        self.run = set_mock('run', side_effect=self.command)
        self.inventory = set_mock('inventory', return_value=self.o)
        self.stable = set_mock('stable_inventory', return_value=self.o)
        self.read = set_mock('read', side_effect=lambda name, default: default)
        self.save = set_mock('save')
        self.restore = set_mock('restore_calibration')
        self.verify = set_mock('verify_calibration')
        set_mock('calibration', return_value=[])
        set_mock('Path')
        self.states = set_mock('service_states', return_value=states())
        set_mock('target_rooms', return_value={'sendspin-zone@one.service', 'sendspin-zone@two.service'})
        self.ct = set_mock('ct', return_value=ROUTING)
        self.user = set_mock('user', return_value='')
        self.physical = set_mock('refresh_physical')
        self.idle = set_mock('wait_idle')
        self.graph = set_mock('verify_graph')
        self.apply = set_mock('apply_grants')

    def tearDown(self):
        for p in reversed(self.patches): p.stop()

    def command(self, args, **kwargs):
        self.calls.append(args)
        if args[1] == 'status':
            return 'status: stopped' if any(a[1] == 'shutdown' for a in self.calls) else 'status: running'
        return ''

    def test_stopped_CT_never_started_or_scanned(self):
        self.run.side_effect = None; self.run.return_value = 'status: stopped'
        self.assertIn('left stopped', r.recover(self.c)['outcome'])
        self.stable.assert_not_called(); self.restore.assert_not_called(); self.apply.assert_not_called()

    def test_duplicate_generation_does_not_restart_or_consume_budget(self):
        self.read.side_effect = lambda name, default: self.o if name == 'observed.json' else default
        self.assertIn('no restart', r.recover(self.c)['outcome'])
        self.restore.assert_not_called(); self.user.assert_not_called(); self.save.assert_not_called()

    def test_same_nodes_refresh_physical_outputs_without_CT_cycle(self):
        result = r.recover(self.c)
        self.assertEqual(result['action'], 'physical adapter refresh')
        self.assertFalse(any(a[1] in ['shutdown', 'start', 'set'] for a in self.calls))
        self.graph.assert_called_once(); self.apply.assert_not_called(); self.physical.assert_called_once()
        self.user.assert_not_called(); self.idle.assert_not_called()

    def test_removed_card_retains_grants_and_checks_remaining_graph(self):
        self.o = observed(None, 4); self.inventory.return_value = self.stable.return_value = self.o
        result = r.recover(self.c)
        self.assertEqual(result['present'], ['CARD_B']); self.apply.assert_not_called()

    def test_intentionally_stopped_room_stays_out_of_participants(self):
        self.states.return_value = states(stopped=['sendspin-zone@two.service'])
        self.assertEqual(r.recover(self.c)['active_rooms'], 1)

    def test_target_stop_does_not_restore_mixers_or_restart(self):
        self.states.return_value = states(stopped=['sendspin-zones.target'])
        with self.assertRaisesRegex(RuntimeError, 'deliberately stopped'): r.recover(self.c)
        self.restore.assert_not_called(); self.user.assert_not_called()

    def test_changed_nodes_use_supported_CT_lifecycle(self):
        self.o = observed(5, 6); self.inventory.return_value = self.stable.return_value = self.o
        result = r.recover(self.c)
        self.assertIn('CT restart', result['action'])
        self.assertEqual([a[1] for a in self.calls], ['status', 'shutdown', 'status', 'start'])
        self.apply.assert_called_once()
        self.idle.assert_called_once()

    def test_busy_streams_prevent_CT_shutdown(self):
        self.o = observed(5, 6); self.inventory.return_value = self.stable.return_value = self.o
        self.idle.side_effect = RuntimeError('streams busy')
        with self.assertRaisesRegex(RuntimeError, 'streams busy'): r.recover(self.c)
        self.assertFalse(any(a[1] == 'shutdown' for a in self.calls)); self.apply.assert_not_called()

    def test_changed_nodes_with_room_maintenance_do_not_cycle_CT(self):
        self.o = observed(5, 6); self.inventory.return_value = self.stable.return_value = self.o
        self.states.return_value = states(stopped=['sendspin-zone@two.service'])
        with self.assertRaisesRegex(RuntimeError, 'intentionally stopped'): r.recover(self.c)
        self.assertFalse(any(a[1] == 'shutdown' for a in self.calls))

    def test_failed_shutdown_never_changes_grants_or_starts(self):
        self.o = observed(5, 6); self.inventory.return_value = self.stable.return_value = self.o
        def fail(args, **kwargs):
            if args[1] == 'shutdown': raise RuntimeError('shutdown refused')
            return self.command(args, **kwargs)
        self.run.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, 'shutdown refused'): r.recover(self.c)
        self.apply.assert_not_called(); self.assertFalse(any(a[1] == 'start' for a in self.calls))

    def test_changed_hardware_aborts_before_audio_restart(self):
        self.inventory.return_value = observed(None, 4)
        with self.assertRaisesRegex(RuntimeError, 'hardware changed'): r.recover(self.c)
        self.user.assert_not_called()

    def test_CT_config_race_aborts_before_restart(self):
        self.config.side_effect = [self.conf, {**self.conf, 'memory': '2048'}]
        with self.assertRaisesRegex(RuntimeError, 'configuration changed'): r.recover(self.c)
        self.user.assert_not_called()

    def test_boot_missing_all_cards_cleans_grants_without_starting_CT(self):
        self.run.side_effect = None; self.run.return_value = 'status: stopped'
        self.inventory.return_value = self.stable.return_value = {}
        result = r.recover(self.c, boot=True)
        self.apply.assert_called_once_with(self.c, self.conf, {})
        self.assertIn('onboot owns startup', result['outcome']); self.user.assert_not_called()

    def test_boot_running_CT_is_not_reconfigured(self):
        result = r.recover(self.c, boot=True)
        self.assertIn('already running', result['outcome'])
        self.apply.assert_not_called(); self.restore.assert_not_called()

    def test_flapping_budget_is_bounded_but_manual_recover_is_available(self):
        self.read.side_effect = lambda name, default: [r.time.time()] * 6 if name == 'attempts.json' else default
        with self.assertRaisesRegex(RuntimeError, 'cooldown'): r.recover(self.c)
        self.user.assert_not_called()
        self.assertEqual(r.recover(self.c, force=True)['outcome'], 'recovered')


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = []
        for ident, name, extra in [
            (1, 'card_a', {'api.alsa.path': 'hw:CARD_A,0', 'clock.name': 'clock_a'}),
            (2, 'card_b', {'api.alsa.path': 'hw:CARD_B,0', 'clock.name': 'clock_b'}),
            (3, 'one', {}), (4, 'playback.one', {'target.object': 'card_a'}),
            (5, 'two', {}), (6, 'playback.two', {'target.object': 'card_b'})]:
            p = {'node.name': name, 'audio.channels': 8, 'audio.rate': 48000, 'audio.format': 'S16LE',
                 'node.dont-fallback': True, 'node.dont-move': True, **extra}
            self.graph.append({'id': ident, 'type': 'PipeWire:Interface:Node', 'info': {'props': p}})
        for ident, channel in [(11, 'FL'), (12, 'FR'), (13, 'RL'), (14, 'RR')]:
            self.graph.append({'id': ident, 'type': 'PipeWire:Interface:Port', 'info': {'props': {'audio.channel': channel}}})
        for ident, output, target, port in [(21, 4, 1, 11), (22, 4, 1, 12), (23, 6, 2, 13), (24, 6, 2, 14)]:
            self.graph.append({'id': ident, 'type': 'PipeWire:Interface:Link',
                               'info': {'output-node-id': output, 'input-node-id': target, 'input-port-id': port}})

    def verify(self, hardware=None):
        with patch.object(r, 'user', return_value=json.dumps(self.graph)):
            r.verify_graph(config(), observed() if hardware is None else hardware, r.routes(ROUTING))

    def test_exact_two_card_stereo_graph_accepted(self):
        self.verify()

    def test_wrong_room_link_rejected(self):
        next(x for x in self.graph if x['id'] == 21)['info']['input-node-id'] = 2
        with self.assertRaisesRegex(RuntimeError, 'wrong physical'): self.verify()

    def test_missing_stereo_channel_rejected(self):
        self.graph = [x for x in self.graph if x['id'] != 22]
        with self.assertRaisesRegex(RuntimeError, 'stereo pair'): self.verify()

    def test_missing_hardware_has_no_fallback_links(self):
        self.graph = [x for x in self.graph if x['id'] not in {1, 21, 22}]
        self.verify(observed(None, 4))
        next(x for x in self.graph if x['id'] == 23)['info']['output-node-id'] = 4
        with self.assertRaises(RuntimeError): self.verify(observed(None, 4))

    def test_shared_physical_clock_rejected(self):
        next(x for x in self.graph if x['id'] == 2)['info']['props']['clock.name'] = 'clock_a'
        with self.assertRaisesRegex(RuntimeError, 'physical clock'): self.verify()

    def test_both_cards_absent_preserves_only_virtual_rooms(self):
        self.graph = [x for x in self.graph if x['id'] not in {1, 2, 21, 22, 23, 24}]
        self.verify({})


class AdapterTests(unittest.TestCase):
    def definitions(self):
        return [{'factory': 'adapter', 'args': {'factory.name': 'api.alsa.pcm.sink',
                 'node.name': 'card_' + letter.lower(), 'api.alsa.path': 'hw:CARD_' + letter + ',0',
                 'audio.channels': 8, 'audio.rate': 48000, 'audio.format': 'S16LE', 'media.class': 'Audio/Sink',
                 'clock.name': 'clock_' + letter, 'adapter.auto-port-config': {'mode': 'dsp'}}}
                for letter in ['A', 'B']]

    def test_definitions_come_from_vendor_converted_existing_configuration(self):
        source = self.definitions()
        with patch.object(r, 'user', return_value=json.dumps(source)) as command:
            result = r.native_adapters(config())
        self.assertTrue(result['card_a']['object.linger'])
        self.assertNotIn('object.linger', source[0]['args'])
        self.assertEqual(result['card_a']['adapter.auto-port-config'], {'mode': 'dsp'})
        self.assertIn('pw-config -n pipewire.conf merge context.objects | spa-json-dump', command.call_args.args)

    def test_unmanaged_or_duplicate_adapter_rejected_before_mutation(self):
        source = self.definitions()
        for objects in [source + [source[0]], source[:1],
                        [{**source[0], 'args': {**source[0]['args'], 'node.name': 'foreign'}}, source[1]]]:
            with patch.object(r, 'user', return_value=json.dumps(objects)), self.assertRaises(RuntimeError):
                r.native_adapters(config())

    def test_only_changed_card_is_recreated(self):
        old = observed(); new = observed(); new['CARD_A']['card_instance'] += 1
        graph = [{'id': i, 'type': 'PipeWire:Interface:Node', 'info': {'props': {'node.name': name}}}
                 for i, name in [(10, 'card_a'), (11, 'card_b')]]
        calls = []
        def command(c, *args):
            calls.append(args)
            return json.dumps(graph) if args[0] == 'pw-dump' else ''
        with patch.object(r, 'native_adapters', return_value={'card_a': {'node.name': 'card_a'}, 'card_b': {'node.name': 'card_b'}}), \
             patch.object(r, 'still_enabled'), patch.object(r, 'inventory', return_value=new), \
             patch.object(r, 'user', side_effect=command):
            r.refresh_physical(config(), new, old)
        self.assertEqual([x[:3] for x in calls], [('pw-dump',), ('pw-cli', 'destroy', '10'), ('pw-cli', 'create-node', 'adapter')])
        self.assertEqual(json.loads(calls[-1][3])['node.name'], 'card_a')

    def test_removed_card_is_destroyed_without_creation_or_healthy_card_restart(self):
        graph = [{'id': 10, 'type': 'PipeWire:Interface:Node', 'info': {'props': {'node.name': 'card_a'}}}]
        with patch.object(r, 'native_adapters', return_value={}), patch.object(r, 'still_enabled'), \
             patch.object(r, 'inventory', return_value=observed(None, 4)), \
             patch.object(r, 'user', side_effect=[json.dumps(graph), '']) as command:
            r.refresh_physical(config(), observed(None, 4), observed())
        self.assertEqual(command.call_count, 2)
        self.assertEqual(command.call_args.args[1:], ('pw-cli', 'destroy', '10'))


if __name__ == '__main__':
    unittest.main()
