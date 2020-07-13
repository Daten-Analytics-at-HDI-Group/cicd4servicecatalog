import logging
import boto3
import os

# Set log level
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.root.setLevel(logging.getLevelName(log_level))  # type: ignore
logger = logging.getLogger(__name__)

servicecatalog_client = boto3.client("servicecatalog")
sts_client = boto3.client("sts")

iam_role_list = [
    "HDI-IAM-role-ReadOnlyAccess",
    "HDI-IAM-role-PowerUserAccess",
    "HDI-IAM-role-AdminAccess",
]

PORTFOLIO_ID = os.getenv("PORTFOLIO_ID")


def assign_principals_for_servicecatalog(
    event, context, client_service_catalog=servicecatalog_client, client_sts=sts_client
):
    """Assign a principal in a foreign AWS account from Service Catalog CICD.

    Args:
        event: The Lambda event object
        context: The Lambda context object
        client_service_catalog: The boto3 Service Catalog client
        client_sts: The boto3 Security Token Service Catalog client

    Returns:
        No returns.
    """
    logger.info("Starting to assign principal ...")
    logger.info(event)
    logger.info(context)
    response = client_sts.get_caller_identity()
    account = response["Account"]
    try:
        logger.info("Listing portfolio in this account {} ...".format(account))
        client_service_catalog.describe_portfolio(Id=PORTFOLIO_ID)
    except Exception as e:
        logger.error("Error while listing portfolio in this ... {}".format(e))
        raise e
    for iam_role in iam_role_list:
        try:
            logger.info(
                "Trying to assign {} in this account {} ...".format(iam_role, account)
            )
            client_service_catalog.associate_principal_with_portfolio(
                AcceptLanguage="en",
                PortfolioId=PORTFOLIO_ID,
                PrincipalARN="arn:aws:iam::{}:role/{}".format(account, iam_role),
                PrincipalType="IAM",
            )
            logger.info(response)
        except Exception as e:
            logger.error(
                """
                Error while assigning {} with portfolio in foreign account {} ... {}
                """.format(
                    iam_role, account, e
                )
            )
            raise e
