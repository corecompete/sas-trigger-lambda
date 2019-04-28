import paramiko
import boto3
import sys
import urllib
import os
import dns.resolver
from botocore.config import Config
from time import gmtime, strftime, sleep
import re
import aws_lambda_logging
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class TriggerException(Exception):
    pass
def lambda_handler(event, context):
    global conn
    aws_lambda_logging.setup(level='DEBUG', boto_level='CRITICAL')
    st_dt_tm = str(strftime("%Y%m%d%H%M%S", gmtime()))
  
    #---------List of Resources
    ev_type = event['Records'][0]['eventName']
    host = os.environ['host']
    bucketName = event['Records'][0]['s3']['bucket']['name']
    input_filename = event['Records'][0]['s3']['object']['key']
    s3keysplit=re.split('/', input_filename)
    s3prefix=s3keysplit[0]
    ssh_user = os.environ['ssh_username']
    s3bucketname = os.environ['bucketname']
    s3prefixname = os.environ['prefix']
    envvariable = sorted(os.environ.keys())

    #---------Create SSH Connection to the Test Ops DI Server
    
    def connect_ssh():
        
        try:
            s3 = boto3.client('s3')
            #-----Download private key file from secure S3 bucket
            s3.download_file(str(s3bucketname),str(s3prefixname), '/tmp/id_rsa')
            logger.info("Private key successfully downloaded from S3 bucket:" + " " + s3bucketname)   
            key = paramiko.RSAKey.from_private_key_file('/tmp/id_rsa')
            conn = paramiko.SSHClient()
            conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            conn.connect(host,username=ssh_user,pkey=key, timeout=30)
            logger.info("Successfully connected to SAS DI Server:" + " " + host)
            return conn
        except FileNotFoundError as file_error:
            logger.error("FileNotFoundError: %s" %file_error)
            sys.exit(1)
        except paramiko.AuthenticationException:
           logger.error("Authentication failed, please verify ssh username: %s")
           sys.exit(1)
        except paramiko.SSHException as sshException:
           logger.error("Unable to establish SSH connection: %s" % sshException)
           sys.exit(1)
        except Exception as e:
           logger.error("Could not open a connection: %s" % e)
           sys.exit(1)
        except paramiko.BadHostKeyException as badHostKeyException:
           logger.error("Unable to verify server's host key: %s" % badHostKeyException)
           sys.exit(1)
            
    #---------Running SSH commands to complete the action
    #if ev_type == 'ObjectCreated:Put':
    if (ev_type[:13] == 'ObjectCreated'):
        conn = connect_ssh()
        
        num_of_triggers = 0
        for envkeys in envvariable:
            if (envkeys[:7]=='trigger'):
                num_of_triggers = num_of_triggers + 1
        logger.info("no of iterations, total count of trigger(s) in the environment variables of Lambda function:" + " " + str(num_of_triggers))               
        for count in range(num_of_triggers):
            logger.info("Iteration: %s" % str(count+1))
            info = os.environ['trigger'+str(count+1)].split(',')
            s3_loc = str(s3prefix) + "/" + info[1]
            script = info[2]
            msgs = info[0]
            shellscript =  str(script) + " " + str(bucketName) + " " + str(s3prefix) + " " + str('&')
            if input_filename.find(s3_loc) > -1: #and input_filename.find(".csv.marker") > -1:
                logger.info("shell script execution process started:" + " " + msgs)          
                try:
                    sftp = conn.open_sftp()
                    sftp.stat(script)
                    logger.info("running script on SAS DI Server:" + " " + shellscript)
                    stdin , stdout, stderr = conn.exec_command(shellscript)
                    logger.warning(stdout.read())
                    logger.info("shell script execution process completed:" + " " +msgs)                     
                except Exception as sftp_error:
                    logger.error("exception occured while running shell script in SAS DI Server: '%s'" % sftp_error)
                
                message = {
                    'Message' : "get "+msgs+" script execution completed. See Cloudwatch logs for complete output"
                }
                break
            else:
                message = ""
        if not message:
            logger.error("The S3 event key prefix value does not match with the trigger values in Lambda function environment variable")
            sys.exit(1)
        conn.close()
        return message