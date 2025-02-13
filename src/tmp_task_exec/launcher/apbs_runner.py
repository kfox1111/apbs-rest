import string, sys, os, time, errno, shutil, tempfile, urllib, copy, pickle, glob
import subprocess
from multiprocessing import Process

from requests import get
from json import loads

from tmp_task_exec import executor_utils
from tmp_task_exec.legacy.apbs_old_utils import fieldStorageToDict, pqrFileCreator, redirector

from tmp_task_exec.legacy.src.aconf import INSTALLDIR, TMPDIR, APBS_LOCATION
from tmp_task_exec.legacy.src.utilities import (getTrackingScriptString, 
                                                getEventTrackingString,
                                                startLogFile,
                                                resetLogFile)

def download_file(job_id, file_name, dest_path, storage_host):
    try:

        object_name = '%s/%s' % (job_id, file_name)
        response = get('%s/api/storage/%s/%s?json=true' % (storage_host, job_id, file_name))
        object_str = loads(response.content)[object_name]
        with open(dest_path, 'w') as fout:
            fout.write(object_str)
    except Exception as e:
        print('ERROR: %s'%e)

class JobDirectoryExistsError(Exception):
    def __init__(self, expression):
        self.expression = expression

class Runner:
    def __init__(self, storage_host, job_id=None, form=None, infile_name=None):
        self.job_id = None
        self.form = None
        self.infile_name = None
        self.read_file_list = None


        if infile_name is not None:
            self.infile_name = infile_name
        elif form is not None:
            self.form = form
            self.apbsOptions = fieldStorageToDict(form)

        if job_id is not None:
            self.job_id = job_id
        else:
            self.job_id = form['pdb2pqrid']

        self.job_dir = '%s%s%s' % (INSTALLDIR, TMPDIR, self.job_id)
        print(self.job_dir)
        if not os.path.isdir(self.job_dir):
            os.mkdir(self.job_dir)

    def prepare_job(self, storage_host):
        # taken from mainInput()
        print('preparing job execution')
        infile_name = self.infile_name
        form = self.form
        job_id = self.job_id

        # downloading necessary files
        if infile_name is not None:
            infile_dest_path = os.path.join(self.job_dir, infile_name)
            print('downloading infile')
            download_file(job_id, infile_name, infile_dest_path, storage_host)


            print('parsing infile READ section')
            file_list = []
            with open(infile_dest_path, 'r') as fin:
                READ_start = False
                READ_end = False
                for whole_line in fin:
                    line = whole_line.strip()
                    for arg in line.split():
                        # print(line.split())
                        if arg.upper() == 'READ':
                            READ_start = True
                        elif arg.upper() == 'END':
                            READ_end = True
                        else:
                            file_list.append(arg)

                        if READ_start and READ_end:
                            break
                    if READ_start and READ_end:
                        break
            # removes the type of file/format from list (e.g. 'charge pqr')
            print(file_list)
            file_list = file_list[2:]
            self.read_file_list = file_list
            print(file_list)

            print('-----downloading other files-----')
            for name in file_list:
                dest_path = os.path.join(self.job_dir, name)
                download_file(job_id, name, dest_path, storage_host)
            print('---------------------------------')

            # download_file(job_id, infile_name, os.path.join(self.job_dir, infile_name), storage_host)

        elif form is not None:
            # tempPage = "results.html"   

            # apbsOptions = fieldStorageToDict(form)
            apbsOptions = self.apbsOptions

            pqrFileCreator(apbsOptions)

            aoFile = open('%s%s%s/%s-ao' % (INSTALLDIR, TMPDIR, job_id, job_id),'w')
            pickle.dump(apbsOptions, aoFile)
            aoFile.close()


            # taken from apbsExec()

            # Copies PQR file to temporary directory
            pqrFileName = form["pdb2pqrid"] + '.pqr'
            #shutil.copyfile('../pdb2pqr/tmp/%s' % pqrFileName, './tmp/%s/%s' % (job_id, pqrFileName))
            

            # Removes water from molecule if requested by the user
            try:
                if form["removewater"] == "on":
                    os.chdir('%stmp/%s' % (INSTALLDIR, job_id))
                    # os.chdir('./tmp/%s' % job_id)
                    inpath = pqrFileName 
                    print(os.getcwd())
                    infile = open(inpath, "r")
                    outpath = inpath[:-4] + '-nowater' + inpath[-4:]
                    outfile = open(outpath, "w")
                    newinpath = inpath[:-4] + '-water' + inpath[-4:]
                    newoutpath = inpath

                    while 1:
                        line = infile.readline()
                        if line == '':
                            break
                        if "WAT" in line:
                            pass
                        elif "HOH" in line:
                            pass
                        else:
                            outfile.write(line)
                    infile.close()
                    outfile.close()

                    shutil.move(inpath, newinpath)
                    shutil.move(outpath, newoutpath)
                    os.chdir('../../')

            except KeyError:
                pass

    def run_job(self, storage_host):
        job_id = self.job_id
        infile_name = self.infile_name

        currentdir = os.getcwd()

        os.chdir('%s%s%s' % (INSTALLDIR, TMPDIR, job_id))
        print( 'current working directory: %s' %os.getcwd())

        # LAUNCHING APBS HERE
#        statusfile = open('%s%s%s/apbs_status' % (INSTALLDIR, TMPDIR, job_id),'w')
#        statusfile.write("running\n")
#        statusfile.close()
        # print(APBS_LOCATION, 'apbsinput.in')
        print(infile_name)
        print(type(infile_name))
        p = subprocess.Popen([APBS_LOCATION, infile_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        # p = subprocess.Popen([APBS_LOCATION, 'apbsinput.in'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        apbs_stdin = p.stdin
        apbs_stdout = p.stdout
        apbs_stderr  = p.stderr

        startLogFile(job_id, 'apbs_stdout.txt', apbs_stdout.read())
#        stdoutFile=open('%s%s%s/apbs_stdout.txt' % (INSTALLDIR, TMPDIR, job_id), 'w')
#        stdoutFile.write(apbs_stdout.read())
#        stdoutFile.close()

        startLogFile(job_id, 'apbs_stderr.txt', apbs_stderr.read())
#        stderrFile=open('%s%s%s/apbs_stderr.txt' % (INSTALLDIR, TMPDIR, job_id), 'w')
#        stderrFile.write(apbs_stderr.read())
#        stderrFile.close()
        
        startLogFile(job_id, 'apbs_end_time', str(time.time()))
#        endtimefile=open('%s%s%s/apbs_end_time' % (INSTALLDIR, TMPDIR, job_id), 'w')
#        endtimefile.write(str(time.time()))
#        endtimefile.close()

        jobDir = '%s%s%s/' % (INSTALLDIR, TMPDIR, job_id)
        statusStr = "complete\n"
        # statusStr += jobDir + 'apbsinput.in\n'
        # statusStr += jobDir + '%s.pqr\n' % job_id
        # statusStr += jobDir + 'io.mc\n'

        # My own additions/adjustments
        statusStr += '%s%s\n' % (jobDir, infile_name)
        print(statusStr)
        for file_name in self.read_file_list:
            statusStr += '%s%s\n' % (jobDir, file_name)
        statusStr += jobDir + 'io.mc\n'
        # for filename in glob.glob(jobDir+"%s-*.dx" % job_id):
        for filename in glob.glob( '%s*.dx' % jobDir):
            statusStr += (filename+"\n")

        # print(glob.glob(jobDir+"*.dx"))
        # print('%s*.dx' % jobDir)
        # print('')
        # print(os.listdir(jobDir))
        
        # for filename in glob.glob(jobDir+"%s-*.dx" % job_id):
        #     statusStr += (filename+"\n")
        statusStr += jobDir + 'apbs_stdout.txt\n'
        statusStr += jobDir + 'apbs_stderr.txt\n'
        startLogFile(job_id, 'apbs_status', statusStr)

        '''Upload associated APBS run files to the storage service'''
        from workflow import jobutils
        sys.stdout = open('%s/debug_forked_stdout.out' % (jobDir), 'a+')
        sys.stderr = open('%s/debug_forked_stderr.out' % (jobDir), 'a+')
        file_list = os.listdir(jobDir)
        if isinstance(file_list, list):
            try:
                jobutils.send_to_storage_service(storage_host, job_id, file_list, os.path.join(INSTALLDIR, TMPDIR))
            except Exception as err:
                with open('storage_err', 'a+') as fin:
                    fin.write(err)

        # sys.stdout.close()
        # sys.stderr.close()
        
        # probably unnecessary as this is in a separate process anyway
        os.chdir(currentdir)

    def start(self, storage_host):
        # pass
        job_id = self.job_id


        # Prepare job
        self.prepare_job(storage_host)

        # Run PDB2PQR in separate process
        startLogFile(job_id, 'apbs_status', "running\n")

        print('Starting subprocess')
        p = Process(target=self.run_job, args=(storage_host,))
        p.start()

        # self.run_job(storage_host)

        print('Getting redirector')
        redirect = redirector(job_id)

        # Upload initial files to storage service
        file_list = [
            'apbs_status',
            'apbs_start_time',
        ]
        if isinstance(file_list, list):
            executor_utils.send_to_storage_service(storage_host, job_id, file_list, os.path.join(INSTALLDIR, TMPDIR))

            # try:
            #     jobutils.send_to_storage_service(storage_host, job_id, file_list, os.path.join(INSTALLDIR, TMPDIR))
            # except Exception as err:
            #     sys.stderr.write(err)
            #     with open('storage_err', 'a+') as fin:
            #         fin.write(err)

        return redirect