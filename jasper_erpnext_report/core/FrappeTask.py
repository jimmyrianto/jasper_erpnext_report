__author__ = 'luissaguas'


import json
from jnius import PythonJavaClass, java_method

class FrappeTask(PythonJavaClass):
	__javainterfaces__ = ['IFrappeTask']

	def __init__(self, task_id, result):
		super(FrappeTask, self).__init__()
		self.task_id = "Local-" + task_id
		self.result = result

		print "result %s" % result

	@java_method('()V')
	def setReadyTask(self):
		from frappe.async import emit_via_redis
		print "task %s is ready" % self.task_id
		response = {}
		response.update({
			"status": "Success",
			"task_id": self.task_id,
			#"result": json.dumps(self.result)
		})
		#emit_via_redis("task_status_change", response, room="task:" + "local_%s" % self.task_id)
		emit_via_redis("task_status_change", response, "task:" + self.task_id)
