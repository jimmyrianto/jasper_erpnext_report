from __future__ import unicode_literals
__author__ = 'luissaguas'
import frappe
#import os
import re
#from frappe.sessions import get_expiry_period
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr
#from frappe.utils.file_manager import save_file_on_filesystem, delete_file_from_filesystem
import logging
from frappe.modules.import_file import import_doc
#from memcache_stats import MemcachedStats
from ast import literal_eval
#from jasperserver.report import Report
#import telnetlib


_logger = logging.getLogger(frappe.__name__)

jasper_formats = ["pdf", "docx", "xls","ods","odt", "rtf"]
jasper_report_types = ['jasper_print_pdf', 'jasper_print_rtf', 'jasper_print_docx', 'jasper_print_ods',\
						'jasper_print_odt', 'jasper_print_xls', 'jasper_print_all']

jasper_cache_data = [{"mcache":"jaspersession", "db": "tabJasperSessions"},{"mcache":'report_list_all', "db": "tabJasperReportListAll"},\
					{"mcache":'report_list_doctype', "db": "tabJasperReportListDoctype"}]

def before_install():
	frappe.db.sql_ddl("""CREATE TABLE IF NOT EXISTS tabJasperSessions(
		user varchar(255) DEFAULT NULL,
		sessiondata longtext,
		lastupdate datetime(6) DEFAULT NULL,
		status varchar(20) DEFAULT NULL
		)""")

	frappe.db.sql_ddl("""CREATE TABLE IF NOT EXISTS tabJasperReqids(
		reqid varchar(255) DEFAULT NULL,
		data longtext,
		lastupdate datetime(6) DEFAULT NULL,
		KEY reqid (reqid)
		)""")

	frappe.db.sql_ddl("""CREATE TABLE IF NOT EXISTS tabJasperReportListAll(
		name varchar(255) DEFAULT NULL,
		data longtext,
		lastupdate datetime(6) DEFAULT NULL
		)""")

	frappe.db.sql_ddl("""CREATE TABLE IF NOT EXISTS tabJasperReportListDoctype(
		name varchar(255) DEFAULT NULL,
		data longtext,
		lastupdate datetime(6) DEFAULT NULL
		)""")

	'''frappe.db.sql_ddl("""CREATE TABLE IF NOT EXISTS tabJasperSessions(
		user varchar(255) DEFAULT NULL,
		sid varchar(255) DEFAULT NULL,
		sessiondata longtext,
		lastupdate datetime(6) DEFAULT NULL,
		status varchar(20) DEFAULT NULL,
		KEY sid (sid)
		)""")'''

def jasper_report_names_from_db(origin="both", filters_report={}, filters_param={}, filters_permrole={}):
	ret = None
	filters_param = filters_param.update({"parenttype":"Jasper Reports"})
	report_from = {"both":["jasperserver", "localserver"], "local jrxml only":["localserver"], "jasperserver only":["jasperserver"]}
	#get all report names
	rnames = frappe.get_all("Jasper Reports", debug=True, filters=filters_report, fields=["name","jasper_doctype", "jasper_print_all", "jasper_print_docx", "jasper_report_origin",\
													"jasper_print_xls", "jasper_print_ods", "jasper_print_odt", "jasper_print_rtf", "jasper_print_pdf","jasper_dont_show_report",\
													"jasper_param_message", "jasper_report_type"])
	with_param = frappe.get_all("Jasper Parameter", filters=filters_param, fields=["`tabJasper Parameter`.parent as parent", "`tabJasper Parameter`.name as p_name",\
													"`tabJasper Parameter`.jasper_param_name as name", "`tabJasper Parameter`.jasper_param_action",\
													"`tabJasper Parameter`.jasper_param_type", "`tabJasper Parameter`.jasper_param_value", "`tabJasper Parameter`.jasper_param_description"])
	with_perm_role = frappe.get_all("Jasper PermRole", filters=filters_permrole, fields=["`tabJasper PermRole`.parent as parent", "`tabJasper PermRole`.name as p_name" ,"`tabJasper PermRole`.jasper_role", "`tabJasper PermRole`.jasper_can_read"])
	print "*************** name ************ {}".format(rnames)
	if rnames:
		ret = {}
		for r in rnames:
			jasper_report_origin = r.jasper_report_origin.lower() #if r.jasper_report_origin else "jasperserver"
			print "*************** name ************ {} for doctype {} filters {}".format(r.name, r.jasper_doctype, filters_report)
			if jasper_report_origin in report_from.get(origin) and not r.jasper_dont_show_report:
				ret[r.name] = {"Doctype name": r.jasper_doctype, "formats": jasper_print_formats(r),"params":[], "perms":[], "message":r.jasper_param_message,\
							   "jasper_report_type":r.jasper_report_type}
				for report in with_param:
						name = report.parent
						if name == r.name:
							report.pop("parent")
							if report.jasper_param_action == "Automatic":
								#report.pop("jasper_param_action")
								continue
							report.pop("p_name")
							report.pop("jasper_param_action")
							ret[r.name]["params"].append(report)

				for perm in with_perm_role:
						name = perm.parent
						if name == r.name:
							perm.pop("parent")
							ret[r.name]["perms"].append(perm)
	return ret

def jasper_print_formats(doc):
	ret = []
	if int(doc.jasper_print_all) == 0:
		for fmt in jasper_formats:
			if int(doc.get("jasper_print_" + fmt,0) or 0) == 1:
				ret.append(fmt)
	else:
		ret = jasper_formats

	return ret

def insert_jasper_list_all(data, cachename="report_list_all", tab="tabJasperReportListAll"):
		frappe.db.sql("""insert into {0}
			(name, data, lastupdate)
			values ("{1}" , "{2}", NOW())""".format(tab, cachename, str(data['data'])))
		# also add to memcache
		print "inserting data {0} cachename {1}".format(data['data'], cachename)
		jaspersession_set_value(cachename, data)
		frappe.db.commit()

def insert_list_all_memcache_db(data, cachename="report_list_all", tab="tabJasperReportListAll"):
	#data['size'] = len(data)
	print "************* insert_list_all_memcache_db {} len {}".format(data, len(data))
	data['session_expiry'] = get_expiry_period(sessionId=cachename)
	data['last_updated'] = frappe.utils.now()
	#print "inserting data list {}".format(data)
	insert_jasper_list_all({"data":data}, cachename, tab)

def update_jasper_list_all(data, cachename="report_list_all", tab="tabJasperReportListAll"):
		frappe.db.sql("""update {0} set data="{1}",
				lastupdate=NOW() where TIMEDIFF(NOW(), lastupdate) < TIME("{2}")""".format(tab, str(data['data']), get_expiry_period(sessionId=cachename)))
		# also add to memcache
		print "inserting data {0} cachename {1}".format(data['data'], cachename)
		jaspersession_set_value(cachename, data)
		frappe.db.commit()

def update_list_all_memcache_db(data, cachename="report_list_all", tab="tabJasperReportListAll"):
	data['session_expiry'] = get_expiry_period(sessionId=cachename)
	data['last_updated'] = frappe.utils.now()
	old_data = frappe._dict(jaspersession_get_value(cachename) or {})
	new_data = old_data.get("data", {})
	new_data.update(data)
	#new_data['size'] = len(new_data)
	print "updating data list {}".format(data)
	update_jasper_list_all({"data":new_data}, cachename, tab)

def get_jasper_data(cachename, get_from_db=None, *args, **kargs):

		if frappe.local.session['sid'] == 'Guest':
			print "bootsession is Guest"
			return None
		data = get_jasper_session_data_from_cache(cachename)
		if not data:
			data = get_jasper_data_from_db(get_from_db, *args, **kargs)
			print "get_jasper_datas {} args {} kargs {}".format(get_from_db, args, kargs)
			if data:
				#if there is data in db but not in cache then update cache
				user = data.get("user")
				if user:
					d = frappe._dict({'data': data, 'user':data.get("user")})
				else:
					d = frappe._dict({'data': data})
				jaspersession_set_value(cachename, d)
		#return data
		#if data:
			#data = frappe._dict(data)
		return data

"""def get_jasper_data2(cachename, get_from_db=lambda: get_jasper_session_data_from_db):

		if frappe.local.session['sid'] == 'Guest':
			return None
		data = get_jasper_session_data_from_cache(cachename)
		if not data:
			data = get_jasper_data_from_db(get_from_db=get_from_db)
		#return data
		#if data:
			#data = frappe._dict(data)
		return data"""

def get_jasper_session_data_from_cache(sessionId):
		#data = frappe._dict(frappe.cache().get_value("jaspersession:" + self.sid) or {})
		#data = frappe._dict(frappe.cache().get_value("jasper:" + sessionId) or {})
		data = frappe._dict(jaspersession_get_value(sessionId) or {})
		#_logger.info("jasperserver  get_jasper_session_data_from_cache {}".format(data))
		print "******************** getting from cache cachename {} data {}".format(sessionId, data)
		if data:
			session_data = data.get("data", {})
			time_diff = frappe.utils.time_diff_in_seconds(frappe.utils.now(),
				session_data.get("last_updated"))
			expiry = get_expiry_in_seconds(session_data.get("session_expiry"))

			if time_diff > expiry:
				#delete_jasper_session(sessionId, tab)
				#frappe.db.commit()
				_logger.info("JasperServerSession get_jasper_session_data_from_cache {}".format(sessionId))
				data = None

		return data and frappe._dict(data.data)

def get_jasper_data_from_db(get_from_db=None, *args, **kargs):
	#print "get_jasper_data_from_db {}".format(get_from_db)
	if not get_from_db:
		rec = get_jasper_session_data_from_db()
	elif args:
		rec = get_from_db(*args)
	elif kargs:
		nargs = kargs.get("args", None)
		if nargs:
			rec = get_from_db(*nargs)
		else:
			rec = get_from_db(**kargs)
	else:
		rec = get_from_db()

	print "******************** getting from db data {} args {} kargs {}".format(rec, args, kargs)
	if rec:
		#print "rec: {0} expire date {1}".format(rec[0][1], get_expiry_period())
		try:
			data = frappe._dict(eval(rec and rec[0][1] or '{}'))
		except:
			data = None
	else:
		#delete_jasper_session(cachename, "tabJasperReportList")
		data = None
	return data#frappe._dict({'data': data})

def get_jasper_data_from_db2(get_from_db=lambda: get_jasper_session_data_from_db):
	print "get_jasper_data_from_db {}".format(get_from_db())
	rec = get_from_db()()
	print "******************** getting from db data {}".format(rec)
	if rec:
		#print "rec: {0} expire date {1}".format(rec[0][1], get_expiry_period())
		try:
			data = frappe._dict(eval(rec and rec[0][1] or '{}'))
		except:
			data = None
	else:
		#delete_jasper_session(cachename, "tabJasperReportList")
		data = None
	return data#frappe._dict({'data': data})

#def get_jasper_reports_list_all_from_db(reqId):
#	rec = frappe.db.sql("""select reqid, data
#		from tabJasperReqids where
#		TIMEDIFF(NOW(), lastupdate) < TIME(%s) and reqid=%s""", (get_expiry_period(), reqId))
#	return rec

def get_jasper_session_data_from_db():
	rec = frappe.db.sql("""select user, sessiondata
		from tabJasperSessions where
		TIMEDIFF(NOW(), lastupdate) < TIME("{0}") and status='Active'""".format(get_expiry_period("jaspersession")))
	return rec

def jaspersession_get_value(sessionId):
	return frappe.cache().get_value("jasper:" + sessionId)

def jaspersession_set_value(sessionId, data):
	frappe.cache().set_value("jasper:" + sessionId, data)

def delete_jasper_session(sessionId, tab="tabJasperSessions"):
	#frappe.cache().delete_value("jaspersession:" + sid)
	frappe.cache().delete_value("jasper:" + sessionId)
	frappe.db.sql("""delete from {}""".format(tab))
	frappe.db.commit()

def get_expiry_in_seconds(expiry):
		if not expiry: return 3600
		parts = expiry.split(":")
		return (cint(parts[0]) * 3600) + (cint(parts[1]) * 60) + cint(parts[2])

def validate_print_permission(doc):
	for ptype in ("read", "print"):
		if not frappe.has_permission(doc.doctype, ptype, doc):
			raise frappe.PermissionError(_("No {0} permission").format(ptype))

"""def update_doctype_doc(dt, dn, file_path):
	report = Report(None, None)
	jrxml = report.getJrxmlPropertiesFromLocalFile(file_path)
	_logger.info("jasperserver update_doc {}".format(jrxml))
	if jrxml:
		docs = []
		jrxml['updateDate'] = frappe.utils.now()
		for v in jrxml.get('inputControls'):
			c_idx = c_idx + 1
			name = v.get('label')
			doc = set_jasper_parameters(name, dn, c_idx, jrxml)
			docs.append(doc)
		import_all_jasper_remote_reports(docs, force=True)"""
			#set_jasper_parameters(param_name, dn, c_idx, mydict)

def import_all_jasper_remote_reports(docs, force=True):
	frappe.only_for("Administrator")
	frappe.flags.in_import = True
	for doc in docs:
		import_doc(doc, force=force)
		"""
		db_modified = frappe.db.get_value(doc['doctype'], doc['name'], 'modified')
			print "**********doctype {0} docname {1} db_modified {2} import_only_new {3}".format(doc['doctype'], doc['name'], db_modified, data.get('import_only_new'))
			if db_modified and doc.get('modified')==frappe.utils.get_datetime_str(db_modified):
				continue
			elif db_modified and data.get('import_only_new'):
				continue
			#elif db_modified and doc.get('jasper_report_number_copies'):
				#this came from server so keep the already changed value
				#doc['jasper_report_number_copies'] = frappe.db.get_value(doc['doctype'], doc['name'], 'jasper_report_number_copies')
		"""

	frappe.flags.in_import = False
	#save to memcache
	'''if docs:
		data = frappe._dict({'data': frappe._dict({})})
		#data['data'] = docs[0]
		for jdoc in docs:
			data['data'][] = jdoc.jasper_report_path
			data['data']['jasper_report_path'] = jdoc.jasper_report_path

		_logger.info("jasperserver import_all_jasper_reports data[data] {}".format(docs))
		data['data']['last_updated'] = frappe.utils.now()
		data['data']['session_expiry'] = get_expiry_period()
		jaspersession_set_value("jaspersession_report_list", data)
		#frappe.cache().set_value("jasper:jaspersession_report_list", data)'''

def _doctype_from_jasper_doc(value, reportname, mydict):
		doc = {"doctype": reportname, "owner": "Administrator", "modified_by": "administrator"}
		#if value:
		doc["name"] = value
		doc['modified'] = frappe.utils.get_datetime_str(mydict.get('updateDate', None) or frappe.utils.now())
		doc['creation'] = frappe.utils.get_datetime_str(mydict.get('updateDate', None) or frappe.utils.now())

		return doc

def do_doctype_from_jasper(data, reports, force=False):

	docs = []
	p_idx = 0
	#tot_idx = frappe.db.sql("""select count(*) from `tabJasper Parameter`""")[0][0] + 1
	#perm_tot_idx = frappe.db.sql("""select count(*) from `tabJasper PermRole`""")[0][0] + 1
	for key, mydict in reports.iteritems():
		c_idx = 0
		p_idx = p_idx + 1
		uri = mydict.get("uri")
		ignore = False
		report_name = key
		change_name = False
		#if already exists check if has the same path (same report)
		old_names = frappe.db.sql("""select name, jasper_report_path, modified from `tabJasper Reports` where jasper_report_name='%s'""" % (key,), as_dict=1)
		print "old_names {}".format(old_names)
		for obj in old_names:
			if uri == obj.get('jasper_report_path'):
				print "uri in old_name {}".format(uri)
				change_name = False
				if data.get('import_only_new'):
					ignore = True
					break
				else:
					#no need to change if the same date or was changed locally by Administrator. Use force to force update and lose the changes
					time_diff = frappe.utils.time_diff_in_seconds(obj.get('modified'), mydict.get("updateDate"))
					if time_diff >= 0 and not force:
						ignore = True
					else:
						#set to the same name that is in db
						report_name = obj.name
					break
			else:
				#report with same name, must change
				change_name = True
		"""for jasper_report in old_names:
			if jasper_report.jasper_report_path == uri and data.get('import_only_new'):
				ignore = True
				break
			elif jasper_report.jasper_report_path == uri:
				break
			#change name
			report_name = key + "#" + len(old_names)
		"""
		if ignore:
			continue

		if change_name:
			report_name = key + "#" + str(len(old_names))
		if True in [report_name == o.get("name") for o in docs]:
			report_name = key + "#" + str(p_idx)
				#ntot_same_name = frappe.db.sql("""select count(*) from `tabJasper Reports` where jasper_report_name='%s' jasper_report_path='%s'""" % (key, uri))[0][0]
				#print "ntot_same_name {}".format(ntot_same_name)
				#if it has the same path then is the same report, if not necessary, ignore!
				#if data.get('import_only_new'):
				#	continue


		#if ntot_same_name > 0:
			#key = key + "#" + str(ntot_same_name)
		doc = _doctype_from_jasper_doc(report_name, "Jasper Reports", mydict)
		doc["jasper_report_name"] = key
		doc['jasper_report_path'] = uri
		doc['idx'] = p_idx
		doc['jasper_report_origin'] = "JasperServer"
		doc['jasper_all_sites_report'] = 0
		for t in jasper_report_types:
			doc[t]=data.get(t)
		"""doc['jasper_print_pdf'] = data.jasper_print_pdf
		doc['jasper_print_rtf'] = data.jasper_print_rtf
		doc['jasper_print_docs'] = data.jasper_print_docx
		doc['jasper_print_ods'] = data.jasper_print_ods
		doc['jasper_print_odt'] = data.jasper_print_odt
		doc['jasper_print_xlsx'] = data.jasper_print_xlsx
		doc['jasper_print_all'] = data.jasper_print_all"""
		if "double" in uri.lower():
			doc['jasper_report_number_copies'] = "Duplicated"
		elif "triple" in uri.lower():
			doc['jasper_report_number_copies'] = "Triplicate"
		else:
			doc['jasper_report_number_copies'] = data.get("report_default_number_copies")

		if "doctypes" in uri.lower():
			doctypes = uri.strip().split("/")
			doctype_name = doctypes[doctypes.index("doctypes") + 1]
			doc["jasper_report_type"] = "Form"
		else:
			doc["jasper_report_type"] = "Genaral"
			doctype_name = None

		doc["jasper_doctype"] = doctype_name
		doc["query"] = mydict.get("queryString")
		doc["jasper_param_message"] = data.get('jasper_param_message').format(report=key, user=frappe.local.session['user'])#_("Please fill in the following parameters in order to complete the report.")
		#doc['jasper_role'] = "Administrator"
		#doc['jasper_can_read'] = True
		docs.append(doc)

		for v in mydict.get('inputControls'):
			c_idx = c_idx + 1
			name = v.get('label')
			doc = set_jasper_parameters(name, key, c_idx, mydict)
			docs.append(doc)
			#tot_idx = tot_idx + 1

		doc = set_jasper_permissions("JRPERM", key, 1, {'updateDate':frappe.utils.now()})
		docs.append(doc)
		#perm_tot_idx = perm_tot_idx + 1

	#new docs must invalidate cache and db
	if docs:
		#delete_jasper_session("report_list_all", tab="tabJasperReportListAll")
		#delete_jasper_session("report_list_doctype", tab="tabJasperReportListDoctype")
		jaspersession_set_value("report_list_dirt_all", True)
		jaspersession_set_value("report_list_dirt_doc", True)

	_logger.info("jasperserver make_doctype_from_jasper {}".format(docs))

	return docs

def set_jasper_parameters(param_name, parent, c_idx, mydict, param_type="String"):
	action_type = "Ask"
	is_copy = "Other"
	doc = _doctype_from_jasper_doc(param_name, "Jasper Parameter", mydict)
	#set the name here for support the same name from diferents reports
	#can't exist two params with the same name for the same report
	doc["name"] = parent + "_" + param_name#+ str(tot_idx)
	doc["jasper_param_name"] = param_name
	doc['idx'] = c_idx
	doc["jasper_param_type"] = param_type
	doc["param_expression"] = "In"
	if check_queryString_with_param(mydict.get("queryString"), param_name):
		is_copy = "Is for where clause"
		action_type = "Automatic"
	elif param_name in "where_not_clause":
		doc["is_copy"] = "Is for where clause"
		doc["param_expression"] = "Not In"
		action_type = "Automatic"
	elif param_name in "page_number":
		doc["is_copy"] = "Is for page number"
		action_type = "Automatic"
	elif param_name in "for_copies":
		doc["is_copy"] = "Is for copies"
		action_type = "Automatic"
	#doc name
	doc["is_copy"] = is_copy
	doc["jasper_param_action"] = action_type
	doc["jasper_param_description"] = ""
	doc["parent"] = parent#key
	doc["parentfield"] = "jasper_parameters"
	doc["parenttype"] = "Jasper Reports"

	return doc

def set_jasper_permissions(perm_name, parent, c_idx, mydict):
	doc = _doctype_from_jasper_doc(perm_name, "Jasper PermRole", mydict)
	#set the name here for support the same name from diferents reports
	doc["name"] = parent + "_" + perm_name#str(tot_idx)
	doc['idx'] = c_idx
	doc["jasper_role"] = "Administrator"
	doc["jasper_can_read"] = True
	doc["parent"] = parent
	doc["parentfield"] = "jasper_roles"
	doc["parenttype"] = "Jasper Reports"

	return doc

def check_queryString_with_param(query, param):
	ret = False
	#s = re.search(r'\$P{%s}|\$P!{%s}' % (param,param), query, re.I)
	s = re.search(r'\$P{%s}|\$P!{%s}|\$X{[\w\W]*,[\w\W]*, %s}' % (param, param, param), query, re.I)
	print "check_queryString_with_param: {0} param name {1}".format(s, param)
	if s:
		print "found!!!! {}".format(s.group())
		ret = True
	return ret

def check_queryString_param(query, param):
	ret = False
	for q in query:
		text = q.text
		print "queryString {}".format(text)
		ret = check_queryString_with_param(text, param)

	return ret

def check_jasper_doc_perm(perms):
	found = True
	if frappe.local.session['user'] == "Administrator":
		return True
	user_roles = frappe.get_roles(frappe.local.session['user'])
	for perm in perms:
		jasper_can_read = perm.get('jasper_can_read', None)
		jasper_role = perm.get('jasper_role', None)
		print "check_jasper_perm read {0} role {1}".format(jasper_can_read, jasper_role)
		if jasper_role in user_roles and not jasper_can_read:
			found = False
			break
	return found

def check_jasper_perm(perms):
	found = False
	if frappe.local.session['user'] == "Administrator":
		return True
	user_roles = frappe.get_roles(frappe.local.session['user'])
	for perm in perms:
		jasper_can_read = perm.get('jasper_can_read', None)
		jasper_role = perm.get('jasper_role', None)
		print "check_jasper_perm read {0} role {1}".format(jasper_can_read, jasper_role)
		if jasper_role in user_roles and jasper_can_read:
			found = True
			break
	return found

def get_expiry_period(sessionId="jaspersession"):
	#exp_sec = "00:10:00"#frappe.defaults.get_global_default("session_expiry") or "06:00:00"
	reports_names = ["report_list_doctype", "report_list_all"]
	if sessionId in reports_names:
		exp_sec = "24:00:00"
	elif "intern_reqid_" in sessionId or "local_report_" in sessionId:
		exp_sec = "8:00:00"
	else:
		exp_sec = frappe.defaults.get_global_default("jasper_session_expiry") or "12:00:00"

		#incase seconds is missing
		if len(exp_sec.split(':')) == 2:
			exp_sec = exp_sec + ':00'
	#print "expire period iss {}".format(exp_sec)
	return exp_sec

def get_value_param_for_hook(param):
	#if not data and not entered value then get default
	default_value = param.jasper_param_value
	matchObj =re.match(r"^[\"'](.*)[\"']", default_value)
	if matchObj:
		print "default_value with replace {}".format(matchObj.group(1))
		default_value = matchObj.group(1)
	if default_value.startswith("(") or default_value.startswith("[") or default_value.startswith("{"):
		value = literal_eval(default_value)
		print "new param.jasper_param_value {}".format(value)
	else:
		#this is the case when user enter "Administrator" and get translated to "'Administrator'"
		#then we need to convert to "Administrator" or 'Administrator'
		value = [str(default_value)]
	return value

#call hooks for params set as "Is for server hook"
def call_hook_for_param(doc, *args):
	method = "on_jasper_params"
	print "args in call hooks {}".format(args)
	#p = param.jasper_param_name
	"""self = doc
	method = "on_jasper_params"
	if hasattr(self, method) and hasattr(getattr(self, method), "__call__"):
		fn = lambda self, *args, **kwargs: getattr(self, method)(*args, **kwargs)
	else:
		fn = lambda doc, *args, **kwargs: None

	fn.__name__ = "on_jasper_params".encode("utf-8")
	ret = Document.hook(fn)(doc, data, params)"""
	ret = doc.run_method(method, *args)
	return ret

def jasper_params(doc, method, data, params):
	print "hook params hook 2 {}".format(params)
	for param in params:
		if param.get('name') != "name_ids":
			pname = param.get("name")
			attrs = param.get("attrs")
			default_value = param.get("value")
			print "jasper_params hook: doc {0} data {1} pname {2} param {3} default_value {4} method {5}".format(doc, data, pname, attrs.param_expression, default_value, method)
			a = ["'%s'" % t for t in default_value]
			value = "where name %s (%s)" % (attrs.param_expression, ",".join(a))
			if not default_value:
				default_value.append(value)
			else:
				param['value'] = [value]
			print "old_value {0} {1}".format(default_value, param.get('value'))
		else:
			param['value'].append('Guest')

	return params