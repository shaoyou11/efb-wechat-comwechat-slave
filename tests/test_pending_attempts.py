import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
spec=importlib.util.spec_from_file_location('pending',Path(__file__).parents[1]/'efb_wechat_comwechat_slave/pending_files.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PendingAttemptTests(unittest.TestCase):
    def test_crash_after_acceptance_does_not_replay_until_manual_release(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'pending.json';store=m.PendingFileStore(p)
            store.put('video',{'msg':{'msgid':'one'}})
            self.assertTrue(store.begin_delivery('video'))
            restored=m.PendingFileStore(p)
            self.assertFalse(restored.begin_delivery('video'))
            restored.put('video',{'msg':{'msgid':'one'}})
            self.assertFalse(restored.begin_delivery('video'))
            self.assertTrue(restored.release_delivery('video'))
            self.assertTrue(restored.begin_delivery('video'))
            restored.remove('video');self.assertEqual(m.PendingFileStore(p).items(),[])

    def test_failed_claim_writes_nothing_and_does_not_authorize_send(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'pending.json';store=m.PendingFileStore(p)
            store.put('video',{'msg':{'msgid':'one'}})
            with patch.object(store,'_save',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):store.begin_delivery('video')
            self.assertEqual(store.records,m.PendingFileStore(p).records)
            self.assertTrue(store.begin_delivery('video'))

    def test_records_are_not_mutable_aliases(self):
        with TemporaryDirectory() as d:
            store=m.PendingFileStore(Path(d)/'p.json');store.put('v',{'msg':{'msgid':'one'}})
            store.items()[0][1]['msg']['_delivery_attempt_started']=True
            self.assertTrue(store.begin_delivery('v'))

    def test_worker_isolates_bad_file_and_preserves_uncertain_attempt(self):
        import ast
        from types import SimpleNamespace
        from unittest.mock import Mock
        source=(Path(__file__).parents[1]/'efb_wechat_comwechat_slave/ComWechat.py').read_text()
        node=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='handle_file_msg')
        namespace={
            'time':SimpleNamespace(time=lambda:100, sleep=Mock(side_effect=StopIteration)),
            'media_path_state':Mock(side_effect=[OSError('temporary media failure'),'ready']),
            'media_wait_timeout':lambda *args:300,
            'MsgWrapper':lambda *args:args[0], 'MsgProcess':lambda *args:None,
            'MessageID':str, 'delivery_confirmed':lambda r:False,
            'EFBMessageError':RuntimeError,
        }
        exec(compile(ast.Module(body=[node],type_ignores=[]),'worker','exec'),namespace)
        worker=SimpleNamespace(file_msg={
            'bad':({'type':'video','timestamp':0,'msgid':'bad'},None,None),
            'uncertain':({'type':'video','timestamp':0,'msgid':'u'},None,None),
        },file_retry_at={},pending_file_store=Mock(),send_efb_msgs=Mock(return_value=[]),delete_file={},logger=Mock())
        worker.pending_file_store.begin_delivery.return_value=True
        with self.assertRaises(StopIteration):namespace['handle_file_msg'](worker)
        self.assertIn('bad',worker.file_retry_at)
        worker.send_efb_msgs.assert_called_once()
        self.assertTrue(worker.file_msg['uncertain'][0]['_delivery_attempt_started'])
        with self.assertRaises(StopIteration):namespace['handle_file_msg'](worker)
        worker.send_efb_msgs.assert_called_once()
