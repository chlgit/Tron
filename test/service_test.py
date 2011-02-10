from testify import *

from tron import service
from tron import node
from tron.utils import testingutils

def set_instance_up(service_instance):
    service_instance.start_action.exit_status = 0
    service_instance._start_complete_callback()

    service_instance._run_monitor()
    service_instance.monitor_action.exit_status = 0
    service_instance._monitor_complete_callback()

class SimpleTest(TestCase):
    @setup
    def build_service(self):
        self.service = service.Service("Sample Service", "sleep 60 &", node_pool=testingutils.TestPool())
        self.service.pid_file_template = "/var/run/service.pid"
        self.service.count = 2
        
    def test_start(self):
        assert_equal(self.service.state, service.Service.STATE_DOWN)
        
        self.service.start()
        assert_equal(self.service.machine.state, service.Service.STATE_STARTING)
        for instance in self.service.instances:
            assert_equal(instance.state, service.ServiceInstance.STATE_STARTING)
        
            set_instance_up(instance)
    
            assert_equal(instance.state, service.ServiceInstance.STATE_UP)
        assert_equal(self.service.state, service.Service.STATE_UP)

    def test_instance_up(self):
        self.service.start()
        instance1, instance2 = self.service.instances
        
        instance1._run_monitor()
        assert_equal(instance1.state, service.ServiceInstance.STATE_MONITORING)

        instance1.monitor_action.exit_status = 0
        instance1._monitor_complete_callback()
        assert_equal(instance1.state, service.ServiceInstance.STATE_UP)
        assert_equal(self.service.state, service.Service.STATE_STARTING)

        instance2._run_monitor()
        instance2.monitor_action.exit_status = 0
        instance2._monitor_complete_callback()

        assert_equal(self.service.state, service.Service.STATE_UP)

    def test_instance_failure(self):
        self.service.start()
        instance1, instance2 = self.service.instances

        instance1.machine.state = service.ServiceInstance.STATE_UP
        instance2.machine.state = service.ServiceInstance.STATE_UP
        self.service.machine.state = service.Service.STATE_UP

        # Fail an instance
        instance2._run_monitor()
        instance2.monitor_action.exit_status = 1
        instance2._monitor_complete_callback()
        
        assert_equal(instance2.state, service.ServiceInstance.STATE_FAILED)
        assert_equal(self.service.state, service.Service.STATE_DEGRADED)

        instance2.stop()

        # Bring it back up
        instance2.start()
        instance2._run_monitor()
        instance2.monitor_action.exit_status = 0
        instance2._monitor_complete_callback()
        
        assert_equal(instance2.state, service.ServiceInstance.STATE_UP)
        assert_equal(self.service.state, service.Service.STATE_UP)

        # Fail both
        instance1._run_monitor()
        instance1.monitor_action.exit_status = 1
        instance1._monitor_complete_callback()

        instance2._run_monitor()
        instance2.monitor_action.exit_status = 1
        instance2._monitor_complete_callback()


        assert_equal(instance1.state, service.ServiceInstance.STATE_FAILED)
        assert_equal(self.service.state, service.Service.STATE_FAILED)
        
class ReconfigTest(TestCase):
    @setup
    def build_service(self):
        self.service = service.Service("Sample Service", "sleep 60 &", node_pool=testingutils.TestPool())
        self.service.pid_file_template = "/tmp/pid"
        self.service.count = 2
    
    def test_absorb_state(self):
        self.service.start()

        new_service = service.Service("Sample Service", "sleep 60 &", node_pool=self.service.node_pool)
        new_service.count = self.service.count
        
        new_service.absorb_previous(self.service)
        
        assert_equal(new_service._last_instance_number, self.service._last_instance_number)
        assert_equal(new_service.state, self.service.state)
        
    
    def test_absorb_count_incr(self):
        self.service.start()
        
        new_service = service.Service("Sample Service", "sleep 60 &", node_pool=self.service.node_pool)
        new_service.count = 3
        self.service.machine.state = service.Service.STATE_DEGRADED
        
        new_service.absorb_previous(self.service)
        assert_equal(len(new_service.instances), new_service.count)
        
        assert_equal(len(set(new_service.instances) - set(self.service.instances)), 1)
        
    def test_absorb_count_decr(self):
        self.service.start()

        new_service = service.Service("Sample Service", "sleep 60 &", node_pool=self.service.node_pool)
        new_service.pid_file_template = "/tmp/pid"
        new_service.count = 1

        new_service.absorb_previous(self.service)
        assert_equal(len(new_service.instances), new_service.count)

        assert_equal(len(set(new_service.instances) - set(self.service.instances)), 0)

class SimpleRestoreTest(TestCase):
    @setup
    def build_service(self):
        self.node_pool = node.NodePool()
        test_node = testingutils.TestNode()
        self.node_pool.nodes.append(test_node)

        self.service = service.Service("Sample Service", "sleep 60 &", node_pool=self.node_pool)
        self.service.pid_file_template = "/tmp/pid"
        self.service.count = 2

        self.service.start()
        instance1, instance2 = self.service.instances
        instance1.machine.state = service.ServiceInstance.STATE_UP
        instance2.machine.state = service.ServiceInstance.STATE_UP
        self.service.machine.state = service.Service.STATE_UP
    
    def test(self):
        data = self.service.data
        
        new_service = service.Service("Sample Service", "sleep 60 &", node_pool=self.node_pool)
        new_service.pid_file_template = "/tmp/pid"
        new_service.count = 2
        new_service.restore(data)
        
        assert_equal(new_service.machine.state, service.Service.STATE_UP)
        assert_equal(len(new_service.instances), 2)
        for instance in new_service.instances:
            assert_equal(instance.state, service.ServiceInstance.STATE_MONITORING)


class FailureRestoreTest(TestCase):
    @setup
    def build_service(self):
        self.node_pool = node.NodePool()
        test_node = testingutils.TestNode()
        self.node_pool.nodes.append(test_node)

        self.service = service.Service("Sample Service", "sleep 60 &", node_pool=self.node_pool)
        self.service.pid_file_template = "/tmp/pid"
        self.service.count = 2

        self.service.start()
        instance1, instance2 = self.service.instances
        instance1.machine.state = service.ServiceInstance.STATE_UP
        instance2.machine.state = service.ServiceInstance.STATE_FAILED
        self.service.machine.state = service.Service.STATE_DEGRADED
    
    def test(self):
        data = self.service.data
        
        new_service = service.Service("Sample Service", "sleep 60 &", node_pool=self.node_pool)
        new_service.pid_file_template = "/tmp/pid"
        new_service.count = 2
        new_service.restore(data)
        
        assert_equal(new_service.machine.state, service.Service.STATE_DEGRADED)
        assert_equal(len(new_service.instances), 2)
        instance1, instance2 = new_service.instances
        assert_equal(instance1.state, service.ServiceInstance.STATE_MONITORING)
        assert_equal(instance2.state, service.ServiceInstance.STATE_MONITORING)
    