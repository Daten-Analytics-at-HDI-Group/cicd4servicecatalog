import configparser
import json
import logging
import os
import uuid
import zipfile
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
LOCAL_ROLE_NAME_SC = os.getenv("LOCAL_ROLE_NAME_SC")
SANDBOX_ACCOUNT_ID = os.getenv("SANDBOX_ACCOUNT_ID")
REPOSITORY_NAME = os.getenv("REPOSITORY_NAME")
PATH_INI = os.getenv("PATH_INI")
PATH = os.getenv("PATH")
BUCKET = os.getenv("BUCKET")
S3_PATH = os.getenv("S3_PATH")

# Set AWS service clients for this account
# For the other accounts, the client will be generated later on within the relevant functions
auto_servicecatalog_client = boto3.client("servicecatalog")
auto_s3_client = boto3.client("s3")
auto_codepipeline_client = boto3.client("codepipeline")
auto_codecommit_client = boto3.client("codecommit")

# List of standard user roles for each account
iam_role_list = [
    "CrossAccountAdmin",
]

# Local role name: Launch Constraint
parsed_string = json.dumps({"LocalRoleName": "{}".format(LOCAL_ROLE_NAME_SC)})


def copy_tested_template(file_name: str, bucket: str, object_name: str):
    """Copy the tested template to the template store in s3.

    Args:
        file_name: File to upload
        bucket: Bucket to upload to
        object_name: S3 object name. If not specified then file_name is used

    Returns:
        True or False
    """
    if object_name is None:
        object_name = file_name

    try:
        logger.info("Copying template file with following parameters ... ")
        logger.info(
            "File name: {} ... String type ? {} ...".format(
                file_name, isinstance(file_name, str)
            )
        )
        logger.info(
            "Bucket name: {} ... String type ?  {} ...".format(
                bucket, isinstance(bucket, str)
            )
        )
        logger.info(
            "Object name: {} ... String type ?  {} ...".format(
                object_name, isinstance(object_name, str)
            )
        )
        auto_s3_client.upload_file(file_name, bucket, object_name)
    except Exception as e:
        logging.error(e)
        return False
    return True


def download_config_file(event):
    """Download and loads the the configuration file via config parser.

    Args:
        event: The CodePipeline event

    Returns:
        config: A meta data configuration object
    """
    try:
        bucket = event["CodePipeline.job"]["data"]["inputArtifacts"][0]["location"][
            "s3Location"
        ]["bucketName"]
        key = event["CodePipeline.job"]["data"]["inputArtifacts"][0]["location"][
            "s3Location"
        ]["objectKey"]
        tmp_file = "/tmp/" + str(uuid.uuid4())
        auto_s3_client.download_file(bucket, key, tmp_file)
        with zipfile.ZipFile(tmp_file, "r") as zip:
            zip.extractall("/tmp/")
            logger.info("Extract Complete")

        config = configparser.ConfigParser()
        config.read("/tmp/" + PATH_INI)

        logger.info("Loaded config file")
        logger.info(config)
    except Exception as e:
        logger.error("Error downloading the config.ini ... {}".format(e))  #
        raise e
    return config


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


def split_path(path: str):
    """Format a path for easier comparision.

    Args:
        path: A systems path like src/conf/file.txt

    Returns:
        file_name: The file name
        short_file_name: The file name without a suffix
    """
    file_name = os.path.split(path)[-1]
    short_file_name = file_name.split(".")[0]
    return file_name, short_file_name


def format_string_and_filenames(path: str,):
    """Use split_path() and escape_and_lower_characters() to format string accordingly.

    Args:
        path: Path of a deleted, modified or newly created file within the Git Repository

    Returns:
        formatted_string: string formatted
        file_name: string formatted
        short_file_name: string formatted
    """
    file_name, short_file_name = split_path(path)
    formatted_string = escape_and_lower_characters(file_name)
    short_file_name = escape_and_lower_characters(short_file_name)
    return formatted_string, file_name, short_file_name


def update_portfolio(
    config,
    added_files: str,
    portfolio_id: str,
    modified_files: str,
    product_ids: list,
    product_names: list,
):
    """Orchestrate function to update the Servicecatalog. This function distinguishes new products and updates.

    Args:
        modified_files: List with modified files
        added_files: List with newly added files
        config: config object from download_config_file
        portfolio_id: Id of the portfolio,
        product_ids: List with all current product_ids
        product_names: List with all current product_names

    Returns:
        No return.
    """
    logger.info("New CodePipeline execution detected ...")
    logger.info("This files has been added {}".format(added_files.split(",")))
    logger.info("This files has been updated {}".format(modified_files.split(",")))

    modifications = added_files.split(",") + modified_files.split(",")
    for template in modifications:
        if template.find(PATH) is not -1:
            logger.info("This file have relevant changes {}".format(template))
            try:
                copy_tested_template(
                    file_name="/tmp/" + template,
                    bucket=BUCKET,
                    object_name=S3_PATH + template.split("/")[2],
                )
                logger.info(
                    """Copied CF-template from {} to template store {} ...
                    """.format(
                        "/tmp/" + template, S3_PATH + template.split("/")[2]
                    )
                )
            except Exception as e:
                logger.error(
                    "Error copying CF-template(s) to template store ... {}".format(e)
                )
                raise e
            try:
                (
                    formatted_string,
                    file_name,
                    short_file_name,
                ) = format_string_and_filenames(path=template)
                logger.info(
                    """Filename: {}. String from for comparison: {}. String for lookup: {}
                    """.format(
                        file_name, formatted_string, short_file_name
                    )
                )
            except Exception as e:
                logger.error(
                    "Error while formatting string for comparision ... {}".format(e)
                )
                raise e
            if short_file_name in product_names:
                index = product_names.index(short_file_name)
                logger.info("Updating existing product in the HDI Servicecatalog ...")
                logger.info(
                    "ID of the product to be updated: {}".format(product_ids[index])
                )
                try:
                    list_provisioning_artifact = auto_servicecatalog_client.list_provisioning_artifacts(
                        AcceptLanguage="en", ProductId=product_ids[index],
                    )
                except Exception as e:
                    logger.error(
                        "Error while listing the existing product provisioning artifacts ... {}".format(
                            e
                        )
                    )
                    raise e
                try:
                    logger.info("Updating constraints ...")
                    delete_constraint(
                        product_id=product_ids[index], portfolio_id=portfolio_id
                    )
                except IndexError:
                    try:
                        create_constraint(
                            product_id=product_ids[index], portfolio_id=portfolio_id
                        )
                    except Exception as e:
                        logger.error(
                            "Error while creating new product constraints ... {}".format(
                                e
                            )
                        )
                        raise e
                try:
                    create_constraint(
                        product_id=product_ids[index], portfolio_id=portfolio_id
                    )
                except Exception as e:
                    logger.error(
                        "Error while creating new product constraints ... {}".format(e)
                    )
                    raise e
                logger.info("Successfully updated product constraint ...")
                try:
                    create_provisioning_artifact_response = auto_servicecatalog_client.create_provisioning_artifact(
                        AcceptLanguage="en",
                        ProductId=product_ids[index],
                        Parameters={
                            "Name": config[file_name]["Name"],
                            "Description": config[file_name]["Diff_Description"],
                            "Info": {
                                "LoadTemplateFromURL": config[file_name]["TemplateURL"],
                            },
                            "Type": config[file_name]["ProductType"],
                            "DisableTemplateValidation": True,
                        },
                    )
                except Exception as e:
                    logger.error(
                        "Error while creating the new product provisioning artifact ... {}".format(
                            e
                        )
                    )
                    raise e
                try:
                    logger.info("Updating provisioning artifact ...")
                    auto_servicecatalog_client.update_provisioning_artifact(
                        AcceptLanguage="en",
                        ProductId=product_ids[index],
                        ProvisioningArtifactId=create_provisioning_artifact_response[
                            "ProvisioningArtifactDetail"
                        ]["Id"],
                        Name=config[file_name]["Version"],
                        Description=config[file_name]["Diff_Description"],
                        Active=True,
                        Guidance="DEFAULT",
                    )
                except Exception as e:
                    logger.error(
                        "Error while updating the new product provisioning artifact ... {}".format(
                            e
                        )
                    )
                    raise e
                try:
                    auto_servicecatalog_client.delete_provisioning_artifact(
                        AcceptLanguage="en",
                        ProductId=product_ids[index],
                        ProvisioningArtifactId=list_provisioning_artifact[
                            "ProvisioningArtifactDetails"
                        ][0]["Id"],
                    )
                except Exception as e:
                    logger.error(
                        "Error while deleting the existing product provisioning artifact ... {}".format(
                            e
                        )
                    )
                    raise e
            else:
                try:
                    logger.info("Creating new Product for the HDI Servicecatalog ...")
                    create_response = auto_servicecatalog_client.create_product(
                        AcceptLanguage="en",
                        Name=config[file_name]["Name"],
                        Owner=config[file_name]["Owner"],
                        Description=config[file_name]["Description"],
                        SupportDescription=config[file_name]["SupportDescription"],
                        SupportEmail=config[file_name]["SupportEmail"],
                        SupportUrl=config[file_name]["SupportUrl"],
                        ProductType=config[file_name]["ProductType"],
                        Tags=[
                            {
                                "Key": config[file_name]["Key_1"],
                                "Value": config[file_name]["Value_1"],
                            }
                        ],
                        ProvisioningArtifactParameters={
                            "Name": config[file_name]["Version"],
                            "Description": config[file_name]["Diff_Description"],
                            "Info": {
                                "LoadTemplateFromURL": config[file_name]["TemplateURL"],
                            },
                            "Type": config[file_name]["ProductType"],
                            "DisableTemplateValidation": True,
                        },
                    )
                    logger.info(create_response)
                    logger.info(
                        "Successfully created a new HDI Servicecatalog product ..."
                    )
                except Exception as e:
                    logger.error("Error while creating a new product ... {}".format(e))
                    raise e
                try:
                    auto_servicecatalog_client.associate_product_with_portfolio(
                        AcceptLanguage="en",
                        ProductId=create_response["ProductViewDetail"][
                            "ProductViewSummary"
                        ]["ProductId"],
                        PortfolioId=portfolio_id,
                    )
                except Exception as e:
                    logger.error(
                        "Error while associating the new product with portfolio ... {}".format(
                            e
                        )
                    )
                    raise e
                try:
                    create_constraint(
                        portfolio_id=portfolio_id,
                        product_id=create_response["ProductViewDetail"][
                            "ProductViewSummary"
                        ]["ProductId"],
                    )
                except Exception as e:
                    logger.error(
                        "Error while creating new constraint for the new product {} within portfolio {} ... {}".format(
                            create_response["ProductViewDetail"]["ProductViewSummary"][
                                "ProductId"
                            ],
                            portfolio_id,
                            e,
                        )
                    )
                    raise e
        else:
            logger.info("No relevant new files detected ...")


def associate_principal_within_this_account(
    iam_roles: list, portfolio_id: str, account_id: str
):
    """Associate IAM Role(s) from this account from the portfolio.

    Args:
        iam_roles: list of IAM roles
        portfolio_id: The portfolio id
        account_id: ID of this account

    Returns:
        No return
    """
    for iam_role in iam_roles:
        try:
            auto_servicecatalog_client.associate_principal_with_portfolio(
                AcceptLanguage="en",
                PortfolioId=portfolio_id,
                PrincipalARN="arn:aws:iam::" + account_id + ":role/{}".format(iam_role),
                PrincipalType="IAM",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.error("Principal does not exists ... {}".format(e))
                pass
        except Exception as e:
            logger.error(
                "Error while associating principals in this account ... {}".format(e)
            )
            raise e


def delete_product(
    product_ids_list: list,
    product_names_list: list,
    deleted_files: list,
    portfolio_id: str,
    config,
):
    """Delete products from the portfolio, which are not mentioned in config.ini.

    Args:
        product_ids_list: Ids of all product within the portfolio
        product_names_list: Names of all product within the portfolio
        deleted_files: list with deleted files from the repository
        portfolio_id: The portfolio id
        config: The parsed config file

    Returns:
        No return.
    """
    sections_list = config.sections()
    formatted_sections_list = []
    formatted_products_list = []
    formatted_deletions_list = []

    for section in sections_list:
        short_section = section.split(".")[0]
        formatted_sections_list.append(escape_and_lower_characters(short_section))

    for product in product_names_list:
        formatted_products_list.append(escape_and_lower_characters(product))

    for deletion in deleted_files:
        formatted_deletions_list.append(escape_and_lower_characters(deletion))

    logger.info(
        """
        The Following products are listed in config.ini {}.
        And these are the products within HDI Servicecatalog: {}
        """.format(
            sections_list, product_names_list
        )
    )
    logger.info(
        """String comparison on sections {} and products {}
        """.format(
            formatted_sections_list, formatted_products_list
        )
    )
    for i in formatted_products_list:
        if i in formatted_deletions_list:
            # if i not in formatted_sections_list:
            index = formatted_products_list.index(i)
            try:
                delete_constraint(
                    product_id=product_ids_list[index], portfolio_id=portfolio_id
                )
            except Exception as e:
                logger.error(
                    """
                Error while deleting constraints for product {} ... {}
                """.format(
                        product_ids_list[index], e
                    )
                )
                raise e
            try:
                auto_servicecatalog_client.delete_product(
                    AcceptLanguage="en", Id=product_ids_list[index]
                )
            except Exception as e:
                logger.error(
                    "Error while deleting the outdated product from the portfolio ... {}".format(
                        e
                    )
                )
                raise e
        else:
            pass


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
            AcceptLanguage="en", ProductId=product_id, PortfolioId=portfolio_id,
        )
        logger.info("Outdated product constraint {} ...".format(constraints_response))
    except Exception as e:
        logger.error(
            "Error listing the outdated product from the portfolio ... {}".format(e)
        )
        raise e
    try:
        logger.info(constraints_response["ConstraintDetails"][0]["ConstraintId"])
        response = auto_servicecatalog_client.delete_constraint(
            Id=constraints_response["ConstraintDetails"][0]["ConstraintId"]
        )
        logger.info("Product constraint {} deleted ...".format(response))
    except IndexError as e:
        logger.error(
            "Error listing portfolio constraint - no one exists... {}".format(e)
        )


def create_constraint(portfolio_id: str, product_id: str):
    """Create product constraints.

    Args:
        portfolio_id: existing portfolio id within the servicecatalog
        product_id: existing product id within the servicecatalog

    Returns:
        No return
    """
    logger.info("Creating constraint on portfolio {} ...".format(portfolio_id))
    try:
        auto_servicecatalog_client.create_constraint(
            PortfolioId=portfolio_id,
            ProductId=product_id,
            Parameters=parsed_string,
            Type="LAUNCH",
            Description="The launch constraint is in line with HDI-IAM-role-AdminAccess",
        )
    except Exception as e:
        logger.error("Error while creating launch constraints ... {}".format(e))
        raise e


def service_catalog_janitor(event, context):
    """Orchestrate all other functions.

    Args:
        event: CodePipeline event
        context: Context of the lambda function

    Returns:
        No return
    """
    logger.info("Starting HDI Service Catalog maintenance ...")
    logger.info(event)
    logger.info(context)

    job_id = event["CodePipeline.job"]["id"]
    job_data = event["CodePipeline.job"]["data"]
    params = get_user_params(job_data)
    logger.info("Found the following user parameters ...")
    logger.info(params)

    portfolio_id = params["portfolio_id"]
    updated_files = params["modified_files"]
    new_files = params["added_files"]
    outdated_files = params["deleted_files"]

    try:
        config = download_config_file(event)
        logger.info("Current config ... {}".format(config))
    except Exception as e:
        put_job_failure(
            codepipeline_client=auto_codepipeline_client,
            job=job_id,
            message="Error downloading config file for product management ... {}".format(
                e
            ),
        )
        raise e
    try:
        list_product_ids, list_product_names = list_products_for_portfolio(
            portfolio_id=portfolio_id
        )
        logger.info("Currently known product ids: {}".format(list_product_ids))
        logger.info("Currently known product names: {}".format(list_product_names))
    except Exception as e:
        logger.error("Error while listing all products ... {}".format(e))
        raise e
    try:
        update_portfolio(
            config=config,
            portfolio_id=portfolio_id,
            modified_files=updated_files,
            added_files=new_files,
            product_ids=list_product_ids,
            product_names=list_product_names,
        )
        logger.info("Updated HDI Service Catalog ...")
    except Exception as e:
        put_job_failure(
            codepipeline_client=auto_codepipeline_client,
            job=job_id,
            message="Error while updating Service Catalog portfolio ... {}".format(e),
        )
        raise e
    if len(outdated_files.split(",")) != 0:
        try:
            logger.info("Checking for product deletion requests ...")
            delete_product(
                product_ids_list=list_product_ids,
                product_names_list=list_product_names,
                portfolio_id=portfolio_id,
                deleted_files=outdated_files.split(","),
                config=config,
            )
            logger.info("Finished product deletion requests ...")
        except Exception as e:
            put_job_failure(
                codepipeline_client=auto_codepipeline_client,
                job=job_id,
                message="Error while deleting outdated HDI Service Catalog products ... {}".format(
                    e
                ),
            )
            raise e
    try:
        logger.info(
            "Assigning principals to portfolio {} in this account ...".format(
                portfolio_id
            )
        )
        associate_principal_within_this_account(
            iam_roles=iam_role_list,
            portfolio_id=portfolio_id,
            account_id=SANDBOX_ACCOUNT_ID,
        )
    except Exception as e:
        put_job_failure(
            codepipeline_client=auto_codepipeline_client,
            job=job_id,
            message="Error while associating IAM roles in this account... {}".format(e),
        )
        raise e
    output_vars = {
        "new_products": new_files,
        "updated_products": updated_files,
    }
    put_job_success(
        codepipeline_client=auto_codepipeline_client,
        job=job_id,
        message="Successfully maintained HDI Servicecatalog ...",
        output_variables=output_vars,
    )
