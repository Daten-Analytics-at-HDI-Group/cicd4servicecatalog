import boto3
import os
import logging
import cfnresponse  # --> https://stackoverflow.com/questions/49885243/aws-lambda-no-module-named-cfnresponse

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.root.setLevel(logging.getLevelName(log_level))  # type: ignore
logger = logging.getLogger(__name__)
response_data = {}


def empty_s3_bucket(bucket):
    """Empty a bucket.

    Args:
        bucket: bucket name

    Returns:
        No return
    """
    s3_client = boto3.client("s3")
    response = s3_client.list_objects_v2(Bucket=bucket)
    if "Contents" in response:
        for item in response["Contents"]:
            print("deleting file", item["Key"])
            s3_client.delete_object(Bucket=bucket, Key=item["Key"])
            while response["KeyCount"] == 1000:
                response = s3_client.list_objects_v2(
                    Bucket=bucket, StartAfter=response["Contents"][0]["Key"],
                )
                for item in response["Contents"]:
                    print("deleting file", item["Key"])
                    s3_client.delete_object(Bucket=bucket, Key=item["Key"])


def empty_bucket(event, context):
    """Orcgestrate the functions on CloudFormation event.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Cloudformation Evtn Resource Ping
    """
    logger.info("Emptying bucket ...")
    logger.info(event)
    logger.info(context)

    bucket_name = event["ResourceProperties"]["BUCKET_NAME"]

    if event["RequestType"] == "Create":
        logger.info("Nothing to do ... ")
        response_data["Message"] = "Success"
        cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
    if event["RequestType"] == "Update":
        logger.info("Nothing to do ... ")
        response_data["Message"] = "Success"
        cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
    if event["RequestType"] == "Delete":
        try:
            logger.info("Deleting all files within bucket {} ... ".format(bucket_name))
            empty_s3_bucket(bucket=bucket_name)
            response_data["Message"] = "Success"
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
        except Exception as e:
            logger.error("An error deleting files ... {}".format(e))
            response_data["Message"] = "Failure"
            cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
