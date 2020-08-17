#!/usr/bin/python3
import os
import sys
import subprocess as sp


cmd_str = 'ip route get 8.8.8.8 | awk -F"src " \'NR==1{split($2,a," ");print a[1]}\''
script_path = os.path.join(os.environ['HOME'], "get_ip_addr.sh")

#-------------------------------------------------------------------------------------

def all_items_in_list_same1(lst):
	return not (any(x != lst[0] for x in lst))

def all_items_in_list_same2(lst):
	return len(set(lst)) == 1

#-------------------------------------------------------------------------------------

def python_version_is_at_least(v=3.7):
	msg = "(Python version is {} {})"
	mv, sv = str(v).split('.')
	if sys.version_info >= (int(mv), int(sv)): 		# if sys.version_info >= (int(v), int(10*v-10*int(v))):
		print(msg.format('at least', v))
		return True
	print(msg.format('less than', v))
	return False

#-------------------------------------------------------------------------------------

def file_is_executable(fpath):
	return os.access(fpath, os.X_OK)

#-------------------------------------------------------------------------------------

def get_ip_addr1():	
	return os.popen(cmd_str).read()[:-1]

def get_ip_addr2():	
	ip_str = str(sp.Popen(cmd_str, shell=True, stdout=sp.PIPE).communicate()[0]).replace('\n', '')
	if sys.version_info < (3,0):
		return ip_str
	return ip_str[2:-3]

def get_ip_addr3():
	ip_str = str(sp.check_output(cmd_str, shell=True)).replace('\n', '')
	if sys.version_info < (3,0):
		return ip_str
	return ip_str[2:-3]

"""
def get_ip_addr4():		## Most secure yet most verbose (doesn't use shell for pipes) -- currently broken
	args = ['ip', 'route', 'get', '8.8.8.8']
	args2 = ['awk', '-F', '"src "', "'NR==1{split($2,a,\" \");print a[1]}'""]
	p_route = sp.Popen(args, stdout=sp.PIPE, shell=False)
	p_awk = sp.Popen(args2, stdin=p_route.stdout, stdout=sp.PIPE, shell=False)
	p_route.stdout.close()
	return str(p_awk.communicate()[0])[2:-3]
"""

#-------------------------------------------------------------------------------------

if __name__ == "__main__":
	if os.path.isfile(script_path) and file_is_executable(script_path): 	## Check that script exists & is executable
		ip_addr = str(sp.check_output(script_path, shell=True))[2:-3]
	else:
		## Check Python version -- if 3.7+, then use sp.run() with the new `capture_output` parameter		
		if python_version_is_at_least(3.7): 	# if sys.version_info >= (3, 7):
			ip_addr = sp.run(cmd_str, capture_output=True, shell=True, text=True).stdout[:-1]
		else:
			ip_addrs = [get_ip_addr1(), get_ip_addr2(), get_ip_addr3()]  #, get_ip_addr4()]
			if not (all_items_in_list_same1(ip_addrs) and all_items_in_list_same2(ip_addrs)):
				print("Different IP Address results found:\n\tget_ip_addr1() --> '{}'\n\tget_ip_addr2() --> '{}'\n\tget_ip_addr3() --> '{}'".format(*ip_addrs))  #\n\tget_ip_addr4() --> '{}'".format(*ip_addrs))
			ip_addr = max(ip_addrs, key=len)

	i = 1
	while ip_addr is None or len(ip_addr) < 7:
		funcs = {1:get_ip_addr1, 2:get_ip_addr2, 3:get_ip_addr3}
		ip_addr = funcs[i]()
		i += 1
		if i > 3:
			ip_addr = "UNKNOWN"
			break

	print("\nIP Address:\t{}".format(ip_addr))