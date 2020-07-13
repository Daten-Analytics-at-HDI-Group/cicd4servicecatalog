import boto3
import os
import logging
import cfnresponse  # --> https://stackoverflow.com/questions/49885243/aws-lambda-no-module-named-cfnresponse

log_level = os.environ.get("LOG_LEVEL", "DEBUG")
logging.root.setLevel(logging.getLevelName(log_level))  # type: ignore
logger = logging.getLogger(__name__)
response_data = {}

# Set global parameter
SANDBOX_ACCOUNT_ID = os.getenv("SANDBOX_ACCOUNT_ID")

auto_servicecatalog_client = boto3.client("servicecatalog")
auto_s3_client = boto3.client("s3")
auto_codepipeline_client = boto3.client("codepipeline")
auto_codecommit_client = boto3.client("codecommit")

# List of standard user roles for each account
iam_role_list = [
    "aws-reserved/sso.amazonaws.com/eu-west-1/AWSReservedSSO_AWSAdministratorAccess_f07f7c1f79215dfb",
]


def escape_and_lower_characters(text: str):
    """Format a string for easier comparision.

    Args:
        text: String with special characters to be escaped

    Return:
        text: the escaped string
    """
    chars = "\\`*_{}[]()>#+-.!$/"
    for c in chars:
        text = text.replace(c, "")
    text = text.lower()
    return text


def list_products_for_portfolio(portfolio_id: str):
    """List a product with the Service Catalog Service.

    Args:
        Service Catalog portfolio id

    Returns:
        list_product_ids: list with Service Catalog products ids
        list_formatted_product_names: list with formatted Service Catalog products names
    """
    list_product_ids = []
    list_product_names = []
    list_formatted_product_names = []

    try:
        product_response = auto_servicecatalog_client.search_products_as_admin(
            AcceptLanguage="en", PortfolioId=portfolio_id
        )
    except Exception as e:
        logger.error("Error searching products ... {}".format(e))
        raise e
    for product in product_response["ProductViewDetails"]:
        list_product_ids.append(product["ProductViewSummary"]["ProductId"])
        list_product_names.append(product["ProductViewSummary"]["Name"])
    for product_name in list_product_names:
        product_name = escape_and_lower_characters(product_name)
        list_formatted_product_names.append(product_name)
    return list_product_ids, list_formatted_product_names


def delete_product(
    product_ids_list: list, portfolio_id: str,
):
    """Delete products from the portfolio.

    Args:
        product_ids_list: Ids of all product within the portfolio
        portfolio_id: The portfolio id

    Returns:
        No return.
    """
    for i in product_ids_list:
        try:
            delete_constraint(product_id=i, portfolio_id=portfolio_id)
        except Exception as e:
            logger.error(
                """
                Error while deleting constraints for product {} ... {}
                """.format(
                    i, e
                )
            )
            raise e
        try:
            auto_servicecatalog_client.disassociate_product_from_portfolio(
                AcceptLanguage="en", ProductId=i, PortfolioId=portfolio_id
            )
        except Exception as e:
            logger.error(
                """
                Error while disassociating product {} from portfolio {} ... {}
                """.format(
                    i, portfolio_id, e
                )
            )
            raise e
        try:
            auto_servicecatalog_client.delete_product(AcceptLanguage="en", Id=i)
        except Exception as e:
            logger.error(
                "Error while deleting the outdated product from the portfolio ... {}".format(
                    e
                )
            )


def delete_constraint(product_id: str, portfolio_id: str):
    """Delete all product constraints.

    Args:
        portfolio_id: existing portfolio id within the servicecatalog
        product_id: changing product id

    Returns:
        No return
    """
    try:
        logger.info("Deleting product constraints ...")
        constraints_response = auto_servicecatalog_client.list_constraints_for_portfolio(
            AcceptLanguage="en", PortfolioId=portfolio_id,
        )
        logger.info(
            "Outdated product constraint {} ...".format(
                constraints_response["ConstraintDetails"]
            )
        )
    except Exception as e:
        logger.error(
            "Error listing the outdated product from the portfolio ... {}".format(e)
        )
        raise e
    for i in range(len(constraints_response["ConstraintDetails"])):
        try:
            response = auto_servicecatalog_client.delete_constraint(
                Id=constraints_response["ConstraintDetails"][i]["ConstraintId"]
            )
            logger.info("Product constraint {} deleted ...".format(response))
        except IndexError as e:
            logger.error(
                "Error listing portfolio constraint - no one exists... {}".format(e)
            )


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
            logger.info(
                "Disassociate arn:aws:iam::" + account_id + ":role/{}".format(iam_role)
            )
            response = auto_servicecatalog_client.disassociate_principal_from_portfolio(
                AcceptLanguage="en",
                PortfolioId=portfolio_id,
                PrincipalARN="arn:aws:iam::" + account_id + ":role/{}".format(iam_role),
            )
            logger.info(response)
        except Exception as e:
            logger.error("Error while disassociating principals ... {}".format(e))
            raise e


def remove_portfolio(event, context):
    """Orchestrate all other functions.

    Args:
        event:
        context:

    Returns:
        No returns
    """
    portfolio_id = event["ResourceProperties"]["PORTFOLIO_ID"]

    if event["RequestType"] == "Create":
        logger.info("Nothing to do ...  ")
        response_data["Message"] = "Success"
        cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
    if event["RequestType"] == "Update":
        logger.info("Nothing to do ...  ")
        response_data["Message"] = "Success"
        cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
    if event["RequestType"] == "Delete":
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
            logger.error("Error while unasigning principals ... {}".format(e))
            response_data["Message"] = "Failure"
            cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
        logger.info("Deleting Portfolio products and constraints ...")
        try:
            list_product_ids, list_product_names = list_products_for_portfolio(
                portfolio_id=portfolio_id
            )
        except Exception as e:
            logger.error("Error while listing all products ... {}".format(e))
            response_data["Message"] = "Failure"
            cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
        try:
            logger.info("Checking for product deletion requests ...")
            delete_product(
                product_ids_list=list_product_ids, portfolio_id=portfolio_id,
            )
            logger.info("Finished product deletion requests ...")
        except Exception as e:
            logger.error(
                """
                Error while deleting outdated HDI Service Catalog products ... {}
                """.format(
                    e
                ),
            )
            response_data["Message"] = "Failure"
            cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
    response_data["Message"] = "Success"
    cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
