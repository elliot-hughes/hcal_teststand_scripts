####################################################################
# Type: MODULE                                                     #
#                                                                  #
# Description: This module contains functions for talking to the   #
# ngCCM and the ngccm tool (terribly named).                       #
####################################################################

from re import search
from subprocess import Popen, PIPE
import pexpect
from time import time, sleep
from print_table import *

# FUNCTIONS:
def send_commands(port, cmds):		# Executes ngccm commands in the slowest way, in order to read all of the output.
	log = ""
	raw_output = ""
	if isinstance(cmds, str):
		cmds = [cmds]
	if "quit" not in cmds:
		cmds.append("quit")
	p = pexpect.spawn('ngccm -z -c -p {0}'.format(port))
	log += "----------------------------\nYou ran the following script with the ngccm tool:\n"
	for c in cmds:
#		print ">> {0}".format(c)
		p.sendline(c)
		if c != "quit":
			p.expect("{0} #\s|E.*\n".format(c))		# Sometimes a line will come in looking like "get fec1-ctrl #completions = 65844", which should not be grabbed. (So when there's no whitespace it needs to be E for error.)
			raw_output += p.before + p.after
		log += c + "\n"
	log += "----------------------------\n"
	p.expect(pexpect.EOF)
	raw_output += p.before
	return {
		"output": raw_output.strip(),
		"log": log.strip(),
	}
	
def send_commands_parsed(port, cmds):		# This executes commands as above, but returns the parsed responses in a list of pairs.
	log = ""
	output = []
	if isinstance(cmds, str):
		cmds = [cmds]
	if "quit" not in cmds:
		cmds.append("quit")
	p = pexpect.spawn('ngccm -z -c -p {0}'.format(port))
	log += "----------------------------\nYou ran the following script with the ngccm tool:\n"
	for c in cmds:
		p.sendline(c)
		t0 = time()
		if c != "quit":
			p.expect("{0} #((\s|E).*)\n".format(c))
			t1 = time()
			output.append({
				"cmd": c,
				"result": p.match.group(1).strip(),
				"times": [t0, t1],
			})
		log += c + "\n"
	log += "----------------------------\n"
	return {
		"output": output,
		"log": log.strip(),
	}

def send_commands_fast(port, cmds):		# This executes ngccm commands in a fast way, but some "get" results might not appear in the output.
	log = ""
	raw_output = ""
	if isinstance(cmds, str):
		cmds = [cmds]
	cmds_str = ""
	for c in cmds:
		cmds_str += "{0}\n".format(c)
	cmds_str += "quit\n"
	log += "----------------------------\nYou ran the following script with the uHTRTool:\n\n{0}\n----------------------------".format(cmds_str)
	p = Popen(['printf "{0}" | ngccm -z -c -p {1}'.format(cmds_str, port)], shell = True, stdout = PIPE, stderr = PIPE)
	raw_output_temp = p.communicate()		# This puts the output of the commands into a list called "raw_output_temp" the first element of the list is stdout, the second is stderr.
	raw_output += raw_output_temp[0] + raw_output_temp[1]
	return {
		"output": raw_output,
		"log": log.strip(),
	}

def get_info(port, crate):		# Returns a dictionary of information about the ngCCM, such as the FW versions.
	log =""
	version_fw_mez_major = -1
	version_fw_mez_minor = -1
	command = "get HF{0}-mezz_reg4".format(crate)
	parsed_output = send_commands_parsed(port, command)["output"]
	result = parsed_output[0]["result"]
	cmd = parsed_output[0]["cmd"]
	if "ERROR" not in result:
		version_str_x = "{0:#08x}".format(int(match.group(3),16))
		version_fw_mez_major = int(version_str_x[-2:], 16)
		version_fw_mez_minor = int(version_str_x[-4:-2], 16)
	else:
		log += ">> ERROR: Failed to find FW versions. The command result follows:\n{0} -> {1}".format(cmd, result)
	version_fw_mez = "{0:02d}.{1:02d}".format(version_fw_mez_major, version_fw_mez_minor)
	return {
		"version_fw_mez_major":	version_fw_mez_major,
		"version_fw_mez_minor":	version_fw_mez_minor,
		"version_fw_mez":	version_fw_mez,
		"version_sw":	"?",
		"log":			log.strip(),
	}

def get_status(ts):		# Perform basic checks of the ngCCMs:
	status = {}
	status["status"] = []
	# Check that versions are accessible:
	if ts.name != "bhm":
		for crate in ts.fe_crates:
			ngccm_info = get_info(ts.ngccm_port, crate)
			if (ngccm_info["version_fw_mez_major"] != -1):
				status["status"].append(1)
			else:
				status["status"].append(0)
	# Check the temperature:
	temp = ts.get_temps()[0]
	status["temp"] = temp
	if ts.name == "bhm":
		if (temp != -1) and (temp < 30.5):
			status["status"].append(1)
		else:
			status["status"].append(0)
	else:
		if (temp != -1) and (temp < 37):
			status["status"].append(1)
		else:
			status["status"].append(0)
	return status

def get_status_bkp(ts):		# Perform basic checks of the FE crate backplanes:
	log = ""
	status = {}
	status["status"] = []
	# Enable, reset, and check the BKP power:
	for crate in ts.fe_crates:
		ngccm_output = send_commands_fast(ts.ngccm_port, ["put HF{0}-bkp_pwr_enable 1".format(crate), "put HF{0}-bkp_reset 1".format(crate), "put HF{0}-bkp_reset 0".format(crate)])["output"]
		log += ngccm_output
		ngccm_output = send_commands_fast(ts.ngccm_port, "get HF{0}-bkp_pwr_bad".format(crate))["output"]
		log += ngccm_output
		match = search("{0} # ([01])".format("get HF{0}-bkp_pwr_bad".format(crate)), ngccm_output)
		if match:
			status["status"].append((int(match.group(1))+1)%2)
		else:
			log += "ERROR: Could not find the result of \"{0}\" in the output.".format("get HF{0}-bkp_pwr_bad".format(crate))
			status["status"].append(0)
	return status

# This function should be moved to "qie.py":
def get_qie_shift_reg(ts , crate , slot , qie_list = range(1,5) ):
	
	qie_settings = [ "CalMode", 
			 "CapID0pedestal", 
			 "CapID1pedestal", 
			 "CapID2pedestal", 
			 "CapID3pedestal", 
			 "ChargeInjectDAC", 
			 "DiscOn", 
			 "FixRange", 
			 "IdcBias", 
			 "IsetpBias", 
			 "Lvds", 
			 "PedestalDAC",
			 "RangeSet", 
			 "TGain", 
			 "TimingIref", 
			 "TimingThresholdDAC",
			 "Trim"]
	
	table = [qie_settings]
	qieLabels = ["setting"]
	commands = []
	for qie in qie_list :
		#print qie
		for setting in qie_settings : 
			commands.append("get HF{0}-{1}-QIE{2}_{3}".format(crate,slot,qie,setting))
	
	ngccm_output = send_commands_parsed( ts.ngccm_port , commands )
	
	for qie in qie_list : 
		qieLabels.append("QIE {0}".format(qie))
		values = []
		for i in ngccm_output["output"] : 		
			for setting in qie_settings : 
				if setting in i["cmd"] and "QIE{0}".format(qie) in i["cmd"]:
					values.append( i["result"] )
				
		table.append( values ) 
	
	#print table
	table_ = [ qieLabels ] 
	for i in zip(*table) : 
		table_.append(i)
	
	print_table(table_)
# /FUNCTIONS

if __name__ == "__main__":
	print "Hang on."
	print 'What you just ran is "ngccm.py". This is a module, not a script. See the documentation ("readme.md") for more information.'