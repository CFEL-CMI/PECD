import numpy as np
import os
import subprocess

def create_dirs(params,N_euler_3D):

    os.chdir(params['working_dir'])
    path =  params['job_directory']

    isdir = os.path.isdir(path) 
    if isdir:
        print("job directory exists: " + str(isdir) + ", " + path) 
    else:
        print("creating job directory: " + str(isdir) + ", " + path) 
        os.mkdir(params['job_directory'])
        os.chdir(params['job_directory'])
        os.mkdir("esp")
        os.mkdir("animation")
        os.chdir("esp")
        for irun in range(N_euler_3D):
            os.mkdir(str(irun))
	os.chdir(params['main_dir'])
    return path



def run_propagate(N_euler,N_batches,jobtype,inputfile,jobdir):

	if jobtype == "maxwell":
		print("Submitting SLURM job")
		path = os.getcwd()
		print ("The current working directory is %s" % path)
		START_FILES = os.listdir(path+"/slurm_run")
		os.chdir(path+"/slurm_run")
		print ("Job directory is %s" % path)
		for ibatch in range(N_batches):
			subprocess.call("./master_script.sh " 	+ str(ibatch) 	+\
				 			" " + str(N_batches) + " " + str(N_euler) + " " +\
					 		jobtype + " " + inputfile + " " + jobdir, shell=True)
	
	elif jobtype == "local":
		print("Executing local job")
		path = os.getcwd()
		print ("The current working directory is %s" % path)
		for ibatch in range(N_batches):
			subprocess.call("python3 PROPAGATE.py " 	+ str(ibatch) 	+\
				 			" " + str(N_batches) + " " + str(N_euler) + " "	+\
					 		jobtype + " " + inputfile , shell=True) 

jobtype 	= "maxwell" #maxwell
inputfile 	= "input_n2"
N_euler 	= 1 #number of euler grid points per dimension
N_batches 	= 1


if __name__ == "__main__":    

	import importlib
	input_module = importlib.import_module(inputfile)
	print("jobtype: " + str(jobtype))
	params = input_module.gen_input(jobtype)
	jobdir = create_dirs(params, N_euler**3)
	run_propagate(N_euler,N_batches,jobtype,inputfile,jobdir)