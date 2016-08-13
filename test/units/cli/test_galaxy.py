# (c) 2016, Adrian Likins <alikins@redhat.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import shutil
import tarfile
import tempfile
import yaml

from ansible.compat.six import PY3
from ansible.compat.tests import unittest
from ansible.compat.tests.mock import call, patch

import ansible
from ansible.errors import AnsibleError, AnsibleOptionsError

from ansible.cli.galaxy import GalaxyCLI


class TestGalaxy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        '''creating prerequisites for installing a role; setUpClass occurs ONCE whereas setUp occurs with every method tested.'''
        # class data for easy viewing: role_dir, role_tar, role_name, role_req, role_path

        if os.path.exists("./delete_me"):
            shutil.rmtree("./delete_me")

        # creating framework for a role
        gc = GalaxyCLI(args=["init", "-c", "--offline", "delete_me"])
        gc.parse()
        gc.run()
        cls.role_dir = "./delete_me"
        cls.role_name = "delete_me"

        # making a temp dir for role installation
        cls.role_path = os.path.join(tempfile.mkdtemp(), "roles")
        if not os.path.isdir(cls.role_path):
            os.makedirs(cls.role_path)

        # creating a tar file name for class data
        cls.role_tar = './delete_me.tar.gz'
        cls.makeTar(cls.role_tar, cls.role_dir)

        # creating a temp file with installation requirements
        cls.role_req = './delete_me_requirements.yml'
        fd = open(cls.role_req, "w")
        fd.write("- 'src': '%s'\n  'name': '%s'\n  'path': '%s'" % (cls.role_tar, cls.role_name, cls.role_path))
        fd.close()

    @classmethod
    def makeTar(cls, output_file, source_dir):
        ''' used for making a tarfile from a role directory '''
        # adding directory into a tar file
        try:
            tar = tarfile.open(output_file, "w:gz")
            tar.add(source_dir, arcname=os.path.basename(source_dir))
        except AttributeError: # tarfile obj. has no attribute __exit__ prior to python 2.    7
                pass
        finally:  # ensuring closure of tarfile obj
            tar.close()

    @classmethod
    def tearDownClass(cls):
        '''After tests are finished removes things created in setUpClass'''
        # deleting the temp role directory
        if os.path.exists(cls.role_dir):
            shutil.rmtree(cls.role_dir)
        if os.path.exists(cls.role_req):
            os.remove(cls.role_req)
        if os.path.exists(cls.role_tar):
            os.remove(cls.role_tar)
        if os.path.isdir(cls.role_path):
            shutil.rmtree(cls.role_path)

    def setUp(self):
        self.default_args = []

    def test_init(self):
        galaxy_cli = GalaxyCLI(args=self.default_args)
        self.assertTrue(isinstance(galaxy_cli, GalaxyCLI))

    def test_display_min(self):
        gc = GalaxyCLI(args=self.default_args)
        role_info = {'name': 'some_role_name'}
        display_result = gc._display_role_info(role_info)
        self.assertTrue(display_result.find('some_role_name') >-1)

    def test_display_galaxy_info(self):
        gc = GalaxyCLI(args=self.default_args)
        galaxy_info = {}
        role_info = {'name': 'some_role_name',
                     'galaxy_info': galaxy_info}
        display_result = gc._display_role_info(role_info)
        if display_result.find('\n\tgalaxy_info:') == -1:
            self.fail('Expected galaxy_info to be indented once')

    def test_execute_remove(self):
        # installing role
        gc = GalaxyCLI(args=["install", "--offline", "-p", self.role_path, "-r", self.role_req])
        galaxy_parser = gc.parse()
        gc.run()

        # checking that installation worked
        role_file = os.path.join(self.role_path, self.role_name)
        self.assertTrue(os.path.exists(role_file))

        # removing role
        gc = GalaxyCLI(args=["remove", "-c", "-p", self.role_path, self.role_name])
        galaxy_parser = gc.parse()
        super(GalaxyCLI, gc).run()
        gc.api = ansible.galaxy.api.GalaxyAPI(gc.galaxy)
        completed_task = gc.execute_remove()

        # testing role was removed
        self.assertTrue(completed_task == 0)
        self.assertTrue(not os.path.exists(role_file))

    def test_exit_without_ignore(self):
        ''' tests that GalaxyCLI exits with the error specified unless the --ignore-errors flag is used '''
        gc = GalaxyCLI(args=["install", "--server=None", "-c", "fake_role_name"])

        # testing without --ignore-errors flag
        galaxy_parser = gc.parse()
        with patch.object(ansible.utils.display.Display, "display", return_value=None) as mocked_display:
            # testing that error expected is raised
            self.assertRaises(AnsibleError, gc.run)
            self.assertTrue(mocked_display.called_once_with("- downloading role 'fake_role_name', owned by "))

        # testing with --ignore-errors flag
        gc = GalaxyCLI(args=["install", "--server=None", "-c", "fake_role_name", "--ignore-errors"])
        galalxy_parser = gc.parse()
        with patch.object(ansible.utils.display.Display, "display", return_value=None) as mocked_display:
            # testing that error expected is not raised with --ignore-errors flag in use
            gc.run()
            self.assertTrue(mocked_display.called_once_with("- downloading role 'fake_role_name', owned by "))

    def run_parse_common(self, galaxycli_obj, action):
        with patch.object(ansible.cli.SortedOptParser, "set_usage") as mocked_usage:
            galaxycli_obj.parse()

            # checking that the common results of parse() for all possible actions have been created/called
            self.assertIsInstance(galaxycli_obj.parser, ansible.cli.SortedOptParser)
            self.assertIsInstance(galaxycli_obj.galaxy, ansible.galaxy.Galaxy)
            if action in ['import', 'delete']:
                formatted_call = 'usage: %prog ' + action + ' [options] github_user github_repo'
            elif action == 'info':
                formatted_call = 'usage: %prog ' + action + ' [options] role_name[,version]'
            elif action == 'init':
                formatted_call = 'usage: %prog ' + action + ' [options] role_name'
            elif action == 'install':
                formatted_call = 'usage: %prog ' + action + ' [options] [-r FILE | role_name(s)[,version] | scm+role_repo_url[,version] | tar_file(s)]'
            elif action == 'list':
                formatted_call = 'usage: %prog ' + action + ' [role_name]'
            elif action == 'login':
                formatted_call = 'usage: %prog ' + action + ' [options]'
            elif action == 'remove':
                formatted_call = 'usage: %prog ' + action + ' role1 role2 ...'
            elif action == 'search':
                formatted_call = 'usage: %prog ' + action + ' [searchterm1 searchterm2] [--galaxy-tags galaxy_tag1,galaxy_tag2] [--platforms platform1,platform2] [--author username]'
            elif action == 'setup':
                formatted_call = 'usage: %prog ' + action + ' [options] source github_user github_repo secret'
            calls = [call('usage: %prog [delete|import|info|init|install|list|login|remove|search|setup] [--help] [options] ...'), call(formatted_call)]
            mocked_usage.assert_has_calls(calls)

    def test_parse(self):
        ''' systematically testing that the expected options parser is created '''
        # testing no action given
        gc = GalaxyCLI(args=["-c"])
        self.assertRaises(AnsibleOptionsError, gc.parse)

        # testing action that doesn't exist
        gc = GalaxyCLI(args=["NOT_ACTION", "-c"])
        self.assertRaises(AnsibleOptionsError, gc.parse)

        # testing action 'delete'
        gc = GalaxyCLI(args=["delete", "-c"])
        self.run_parse_common(gc, "delete")
        self.assertEqual(gc.options.verbosity, 0)

        # testing action 'import'
        gc = GalaxyCLI(args=["import", "-c"])
        self.run_parse_common(gc, "import")
        self.assertEqual(gc.options.wait, True)
        self.assertEqual(gc.options.reference, None)
        self.assertEqual(gc.options.check_status, False)
        self.assertEqual(gc.options.verbosity, 0)

        # testing action 'info'
        gc = GalaxyCLI(args=["info", "-c"])
        self.run_parse_common(gc, "info")
        self.assertEqual(gc.options.offline, False)

        # testing action 'init'
        gc = GalaxyCLI(args=["init", "-c"])
        self.run_parse_common(gc, "init")
        self.assertEqual(gc.options.offline, False)
        self.assertEqual(gc.options.force, False)

        # testing action 'install'
        gc = GalaxyCLI(args=["install", "-c"])
        self.run_parse_common(gc, "install")
        self.assertEqual(gc.options.ignore_errors, False)
        self.assertEqual(gc.options.no_deps, False)
        self.assertEqual(gc.options.role_file, None)
        self.assertEqual(gc.options.force, False)

        # testing action 'list'
        gc = GalaxyCLI(args=["list", "-c"])
        self.run_parse_common(gc, "list")
        self.assertEqual(gc.options.verbosity, 0)

        # testing action 'login'
        gc = GalaxyCLI(args=["login", "-c"])
        self.run_parse_common(gc, "login")
        self.assertEqual(gc.options.verbosity, 0)
        self.assertEqual(gc.options.token, None)

        # testing action 'remove'
        gc = GalaxyCLI(args=["remove", "-c"])
        self.run_parse_common(gc, "remove")
        self.assertEqual(gc.options.verbosity, 0)

        # testing action 'search'
        gc = GalaxyCLI(args=["search", "-c"])
        self.run_parse_common(gc, "search")
        self.assertEqual(gc.options.platforms, None)
        self.assertEqual(gc.options.galaxy_tags, None)
        self.assertEqual(gc.options.author, None)

        # testing action 'setup'
        gc = GalaxyCLI(args=["setup", "-c"])
        self.run_parse_common(gc, "setup")

        self.assertEqual(gc.options.verbosity, 0)
        self.assertEqual(gc.options.remove_id, None)
        self.assertEqual(gc.options.setup_list, False)


class ValidRoleTests(object):

    expected_role_dirs = ('defaults', 'files', 'handlers', 'meta', 'tasks', 'templates', 'vars', 'tests')

    @classmethod
    def setUpRole(cls, role_name, galaxy_args=None, skeleton_path=None):
        if galaxy_args is None:
            galaxy_args = []

        if skeleton_path is not None:
            cls.role_skeleton_path = skeleton_path
            galaxy_args += ['--role-skeleton', skeleton_path]

        # Make temp directory for testing
        cls.test_dir = tempfile.mkdtemp()
        if not os.path.isdir(cls.test_dir):
            os.makedirs(cls.test_dir)

        cls.role_dir = os.path.join(cls.test_dir, role_name)
        cls.role_name = role_name

        # create role using default skeleton
        gc = GalaxyCLI(args=['init', '-c', '--offline'] + galaxy_args + ['-p', cls.test_dir, cls.role_name])
        gc.parse()
        gc.run()
        cls.gc = gc
        
        if skeleton_path is None:
            cls.role_skeleton_path = gc.galaxy.default_role_skeleton_path

    @classmethod
    def tearDownClass(cls):
        if os.path.isdir(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def test_metadata(self):
        with open(os.path.join(self.role_dir, 'meta', 'main.yml'), 'r') as mf:
            metadata = yaml.safe_load(mf)
        self.assertIn('galaxy_info', metadata, msg='unable to find galaxy_info in metadata')
        self.assertIn('dependencies', metadata, msg='unable to find dependencies in metadata')

    def test_readme(self):
        readme_path = os.path.join(self.role_dir, 'README.md')
        self.assertTrue(os.path.exists(readme_path), msg='Readme doesn\'t exist')

    def test_main_ymls(self):
        need_main_ymls = set(self.expected_role_dirs) - set(['meta', 'tests', 'files', 'templates'])
        for d in need_main_ymls:
            main_yml = os.path.join(self.role_dir, d, 'main.yml')
            self.assertTrue(os.path.exists(main_yml))
            expected_string = "---\n# {0} file for {1}".format(d, self.role_name)
            with open(main_yml, 'r') as f:
                self.assertEqual(expected_string, f.read().strip())

    def test_role_dirs(self):
        for d in self.expected_role_dirs:
            self.assertTrue(os.path.isdir(os.path.join(self.role_dir, d)), msg="Expected role subdirectory {0} doesn't exist".format(d))

    def test_travis_yml(self):
        with open(os.path.join(self.role_dir,'.travis.yml'), 'r') as f:
            contents = f.read()

        with open(os.path.join(self.role_skeleton_path, '.travis.yml'), 'r') as f:
            expected_contents = f.read()

        self.assertEqual(expected_contents, contents, msg='.travis.yml does not match expected')

    def test_readme_contents(self):
        with open(os.path.join(self.role_dir, 'README.md'), 'r') as readme:
            contents = readme.read()

        with open(os.path.join(self.role_skeleton_path, 'README.md'), 'r') as f:
            expected_contents = f.read()

        self.assertEqual(expected_contents, contents, msg='README.md does not match expected')

    def test_test_yml(self):
        with open(os.path.join(self.role_dir, 'tests', 'test.yml'), 'r') as f:
            test_playbook = yaml.safe_load(f)
        print(test_playbook)
        self.assertEqual(len(test_playbook), 1)
        self.assertEqual(test_playbook[0]['hosts'], 'localhost')
        self.assertEqual(test_playbook[0]['remote_user'], 'root')
        self.assertListEqual(test_playbook[0]['roles'], [self.role_name], msg='The list of roles included in the test play doesn\'t match')


class TestGalaxyInitDefault(unittest.TestCase, ValidRoleTests):

    @classmethod
    def setUpClass(cls):
        cls.setUpRole(role_name='delete_me')

    def test_metadata_contents(self):
        with open(os.path.join(self.role_dir, 'meta', 'main.yml'), 'r') as mf:
            metadata = yaml.safe_load(mf)
        self.assertEqual(metadata.get('galaxy_info', dict()).get('author'), 'your name', msg='author was not set properly in metadata')


class TestGalaxyInitContainerEnabled(unittest.TestCase, ValidRoleTests):

    @classmethod
    def setUpClass(cls):
        cls.setUpRole('delete_me_container', galaxy_args=['--container-enabled'])

    def test_metadata_container_tag(self):
        with open(os.path.join(self.role_dir, 'meta', 'main.yml'), 'r') as mf:
            metadata = yaml.safe_load(mf)
        self.assertIn('container', metadata.get('galaxy_info', dict()).get('galaxy_tags',[]), msg='container tag not set in role metadata')

    def test_metadata_contents(self):
        with open(os.path.join(self.role_dir, 'meta', 'main.yml'), 'r') as mf:
            metadata = yaml.safe_load(mf)
        self.assertEqual(metadata.get('galaxy_info', dict()).get('author'), 'your name', msg='author was not set properly in metadata')

    def test_meta_container_yml(self):
        self.assertTrue(os.path.exists(os.path.join(self.role_dir, 'meta', 'container.yml')), msg='container.yml was not created')

    def test_test_yml(self):
        with open(os.path.join(self.role_dir, 'tests', 'test.yml'), 'r') as f:
            test_playbook = yaml.safe_load(f)
        print(test_playbook)
        self.assertEqual(len(test_playbook), 1)
        self.assertEqual(test_playbook[0]['hosts'], 'localhost')
        self.assertFalse(test_playbook[0]['gather_facts'])
        self.assertEqual(test_playbook[0]['connection'], 'local')
        self.assertIsNone(test_playbook[0]['tasks'], msg='We\'re expecting an unset list of tasks in test.yml')


class TestGalaxyInitSkeleton(unittest.TestCase, ValidRoleTests):

    @classmethod
    def setUpClass(cls):
        role_skeleton_path = os.path.join(os.path.split(__file__)[0], 'test_data', 'role_skeleton')
        cls.setUpRole('delete_me_skeleton', skeleton_path=role_skeleton_path)

    def test_empty_files_dir(self):
        files_dir = os.path.join(self.role_dir, 'files')
        self.assertTrue(os.path.isdir(files_dir))
        self.assertListEqual(os.listdir(files_dir), [], msg='we expect the files directory to be empty, is ignore working?')

    def test_template_ignore_jinja(self):
        test_conf_j2 = os.path.join(self.role_dir, 'templates', 'test.conf.j2')
        self.assertTrue(os.path.exists(test_conf_j2), msg="The test.conf.j2 template doesn't seem to exist, is it being rendered as test.conf?")
        with open(test_conf_j2, 'r') as f:
            contents = f.read()
        expected_contents = '[defaults]\ntest_key = {{ test_variable }}'
        self.assertEqual(expected_contents, contents, msg="test.conf.j2 doesn't contain what it should, is it being rendered?")

    def test_template_ignore_jinja_subfolder(self):
        test_conf_j2 = os.path.join(self.role_dir, 'templates', 'subfolder', 'test.conf.j2')
        self.assertTrue(os.path.exists(test_conf_j2), msg="The test.conf.j2 template doesn't seem to exist, is it being rendered as test.conf?")
        with open(test_conf_j2, 'r') as f:
            contents = f.read()
        expected_contents = '[defaults]\ntest_key = {{ test_variable }}'
        self.assertEqual(expected_contents, contents, msg="test.conf.j2 doesn't contain what it should, is it being rendered?")

    def test_template_ignore_similar_folder(self):
        self.assertTrue(os.path.exists(os.path.join(self.role_dir, 'templates_extra', 'templates.txt')))

    def test_skeleton_option(self):
        self.assertEquals(self.role_skeleton_path, self.gc.get_opt('role_skeleton'), msg='Skeleton path was not parsed properly from the command line')
