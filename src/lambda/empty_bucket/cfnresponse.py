#  Copyright 2016 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
#  This file is licensed to you under the AWS Customer Agreement (the "License").
#  You may not use this file except in compliance with the License.
#  A copy of the License is located at http://aws.amazon.com/agreement/ .
#  This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied.
#  See the License for the specific language governing permissions and limitations under the License.

from botocore.vendored import requests
import json

SUCCESS = "SUCCESS"
FAILED = "FAILED"


def send(
    event,
    context,
    response_status: str,
    response_data: str,
    physical_resource_id=None,
    no_echo=False,
    response_body={},
):
    """Help programming CustomResource within CloudFormation.

    Args:
        event: The Lambda event object
        context: The Lambda context object
        response_status: String with values "Success" or "Failure"
        response_data: A message for response logging
        physical_resource_id: CloudFormation PhysicalResourceId. Default None
        no_echo: CloudFormation echo capabilities. Default False
        response_body: Response object
    Returns:
        No Returns are delivered
    """
    response_url = event["ResponseURL"]

    print(response_url)

    response_body["Status"] = response_status
    response_body["Reason"] = (
        "See the details in CloudWatch Log Stream: " + context.log_stream_name
    )
    response_body["PhysicalResourceId"] = (
        physical_resource_id or context.log_stream_name
    )
    response_body["StackId"] = event["StackId"]
    response_body["RequestId"] = event["RequestId"]
    response_body["LogicalResourceId"] = event["LogicalResourceId"]
    response_body["NoEcho"] = no_echo
    response_body["Data"] = response_data

    json_response_body = json.dumps(response_body)

    print("Response body:\n" + json_response_body)

    headers = {"content-type": "", "content-length": str(len(json_response_body))}

    try:
        response = requests.put(response_url, data=json_response_body, headers=headers)
        print("Status code: " + response.reason)
    except Exception as e:
        print("send(..) failed executing requests.put(..): " + str(e))
