import importlib.util
import errno
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

SCRIPT=Path(__file__).parents[1]/'scripts'/'distribution.py'

class DistributionTests(unittest.TestCase):
    def module(self):
        self.assertTrue(SCRIPT.exists(),'portable installer/packager missing')
        s=importlib.util.spec_from_file_location('distribution',SCRIPT);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
    def fixture(self,root):
        p=root/'skills/demo';p.mkdir(parents=True);(p/'SKILL.md').write_text('---\nname: demo\ndescription: Sample\n---\n')
        (root/'README.md').write_text('Sample package')
        return p
    def test_install_copies_only_selected_skill_and_refuses_overwrite(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)/'src';p=self.fixture(r);(p/'.env').write_text('PRIVATE=never-copy');(p/'__pycache__').mkdir();(p/'__pycache__/x.pyc').write_bytes(b'x')
            dest=Path(d)/'skills';m.install(r,dest,['demo'])
            self.assertTrue((dest/'demo/SKILL.md').exists());self.assertFalse((dest/'demo/.env').exists());self.assertFalse((dest/'demo/__pycache__').exists())
            with self.assertRaises(FileExistsError):m.install(r,dest,['demo'])
    def test_dry_run_does_not_write(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)/'src';self.fixture(r);dest=Path(d)/'dest';m.install(r,dest,['demo'],dry_run=True);self.assertFalse(dest.exists())
    def test_archive_excludes_artifacts_credentials_and_is_reproducible(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)/'src';self.fixture(r);(r/'artifacts').mkdir();(r/'artifacts/private.md').write_text('private');(r/'.env').write_text('secret')
            a=Path(d)/'a.zip';b=Path(d)/'b.zip';m.archive(r,a);m.archive(r,b)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            with zipfile.ZipFile(a) as z:self.assertEqual(set(z.namelist()),{'workplace-toolkit/README.md','workplace-toolkit/skills/demo/SKILL.md'})
    def test_symlink_and_private_source_path_rejected(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)/'src';p=self.fixture(r);(p/'leak.md').symlink_to(r/'README.md')
            with self.assertRaises(ValueError):m.archive(r,Path(d)/'a.zip')
            (p/'leak.md').unlink();(p/'leak.md').write_text('/'+'Users/'+'example-person/private/.env')
            with self.assertRaises(ValueError):m.archive(r,Path(d)/'a.zip')
    def test_unknown_or_path_traversal_skill_rejected(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)/'src';self.fixture(r)
            for name in ['../outside','missing']:
                with self.assertRaises(ValueError):m.install(r,Path(d)/'dest',[name])

    def test_archive_fallback_without_hardlinks_and_no_clobber(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)/'src';self.fixture(r);out=Path(d)/'release.zip'
            with patch.object(m.os,'link',side_effect=OSError(errno.ENOTSUP,'unsupported')):
                m.archive(r,out)
            self.assertTrue(zipfile.is_zipfile(out))
            before=out.read_bytes()
            with self.assertRaises(FileExistsError):m.archive(r,out)
            self.assertEqual(out.read_bytes(),before)

if __name__=='__main__':unittest.main()
