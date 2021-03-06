# -*- mode:python ; fill-column:120 -*-
import time
import unittest

from botoflow import (workflow_time, WorkflowDefinition, WorkflowWorker,
                      signal, execute, return_, workflow_starter,
                      Future)
from utils import SWFMixIn


class SignalledWorkflow(WorkflowDefinition):

    def __init__(self, workflow_execution):
        super(SignalledWorkflow, self).__init__(workflow_execution)
        self.msg = "Not signalled"

    @execute(version='1.0', execution_start_to_close_timeout=60)
    def execute(self):
        yield workflow_time.sleep(4)
        return_(self.msg)

    @signal()
    def signal(self, msg):
        self.msg = msg


class SignalledManyInputWorkflow(WorkflowDefinition):

    @execute(version='1.0', execution_start_to_close_timeout=60)
    def execute(self):
        self._wait_for_signal = Future()
        result = []
        while True:
            signal_result = yield self._wait_for_signal
            if not signal_result:
                break
            result.append(signal_result)
            # reset the future
            self._wait_for_signal = Future()

        return_(result)

    @signal()
    def add_data(self, input):
        self._wait_for_signal.set_result(input)


class TestSignalledWorkflows(SWFMixIn, unittest.TestCase):

    def test_signalled_workflow(self):
        wf_worker = WorkflowWorker(
            self.session, self.region, self.domain, self.task_list,
            SignalledWorkflow)

        with workflow_starter(self.session, self.region, self.domain, self.task_list):
            instance = SignalledWorkflow.execute()
            self.workflow_execution = instance.workflow_execution

            # wait and signal the workflow
            time.sleep(1)
            instance.signal("Signaled")

        for i in range(2):
            wf_worker.run_once()

        time.sleep(1)

        hist = self.get_workflow_execution_history()
        self.assertEqual(len(hist), 11)
        self.assertEqual(hist[-1]['eventType'], 'WorkflowExecutionCompleted')
        self.assertEqual(self.serializer.loads(
            hist[-1]['workflowExecutionCompletedEventAttributes']['result']), 'Signaled')

    def test_signalled_many_input_workflow(self):
        wf_worker = WorkflowWorker(
            self.session, self.region, self.domain, self.task_list,
            SignalledManyInputWorkflow)

        with workflow_starter(self.session, self.region, self.domain, self.task_list):
            instance = SignalledManyInputWorkflow.execute()
            self.workflow_execution = instance.workflow_execution

            # wait and signal the workflow
            for i in range(1, 5):
                instance.add_data(i)
            instance.add_data(None)  # stop looping

        wf_worker.run_once()

        time.sleep(1)

        hist = self.get_workflow_execution_history()
        self.assertEqual(len(hist), 10)
        self.assertEqual(hist[-1]['eventType'], 'WorkflowExecutionCompleted')
        self.assertEqual(self.serializer.loads(
            hist[-1]['workflowExecutionCompletedEventAttributes']['result']),
                         [1,2,3,4])


if __name__ == '__main__':
    unittest.main()

