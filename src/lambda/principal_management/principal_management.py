import os
import logging
import boto3
from botocore.exceptions import ClientError
from servicecatalog import (
    get_user_params,
    put_job_failure,
    put_job_success,
)

# Set log level
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.root.setLevel(logging.getLevelName(log_level))  # type: ignore
logger = logging.getLogger(__name__)

# Set global parameter
SANDBOX_ACCOUNT_ID = os.getenv("SANDBOX_ACCOUNT_ID")

# Set AWS service clients for this account
# For the other accounts, the client will be generated later on within the relevant functions
auto_servicecatalog_client = boto3.client("servicecatalog")
auto_codepipeline_client = boto3.client("codepipeline")
auto_codecommit_client = boto3.client("codecommit")

# List of standard user roles for each account
iam_role_list = [
    "CrossAccountAdmin",
]


def disassociate_principal_within_this_account(
    iam_roles: list, portfolio_id: str, account_id: str
):
    """Disassociate IAM Role(s) from this account from the portfolio.

    Args:
        account_id: the account to run the disassociation process
        iam_roles: list of IAM roles
        portfolio_id: The portfolio id

    Returns:
        No returns
    """
    for iam_role in iam_roles:
        try:
            auto_servicecatalog_client.disassociate_principal_from_portfolio(
                AcceptLanguage="en",
                PortfolioId=portfolio_id,
                PrincipalARN="arn:aws:iam::" + account_id + ":role/{}".format(iam_role),
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.error("Principal does not exists ... {}".forat(e))
                pass
        except Exception as e:
            logger.error("Error while disassociating principals ... {}".format(e))
            raise e


def principal_management(event, context):
    """Orchestrate all other functions.

    Args:
        event: CodePipeline event
        context: Lambda context

    Returns:
        No returns
    """
    logger.info("Building Deployment Environment ...")
    logger.info(event)
    logger.info(context)
    job_id = event["CodePipeline.job"]["id"]
    job_data = event["CodePipeline.job"]["data"]
    params = get_user_params(job_data)
    logger.info("Found the following user parameters ...")
    logger.info(params)

    portfolio_id = params["portfolio_id"]

    try:
        logger.info(
            "Unassigning principals from portfolio {} in this account ...".format(
                portfolio_id
            )
        )
        disassociate_principal_within_this_account(
            iam_roles=iam_role_list,
            portfolio_id=portfolio_id,
            account_id=SANDBOX_ACCOUNT_ID,
        )
    except Exception as e:
        put_job_failure(
            codepipeline_client=auto_codepipeline_client,
            job=job_id,
            message="Error: Cannot disassociate principals in this account ... {}".format(
                e
            ),
        )
        raise e
    output_vars = {"message": "Success"}
    put_job_success(
        codepipeline_client=auto_codepipeline_client,
        job=job_id,
        message="Finished Building Principal Management ...",
        output_variables=output_vars,
    )
