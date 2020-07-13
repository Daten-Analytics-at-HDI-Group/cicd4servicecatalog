import os
import logging
import json
import boto3

from servicecatalog import put_job_success, put_job_failure

# Set loglevel
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.root.setLevel(logging.getLevelName(log_level))
logger = logging.getLogger(__name__)

# Define the environment variables for repository name
REPOSITORY_NAME = os.getenv("REPOSITORY_NAME")

# Set AWS service clients
client_codecommit = boto3.client("codecommit")
client_codepipeline = boto3.client("codepipeline")
client_service_catalog = boto3.client("servicecatalog")


def get_file_changes(repository_name, before_commit_specifier, after_commit_specifier):
    """Get changes between two commits.

    Args:
        repository_name: The repository name
        before_commit_specifier: previous commit specifier
        after_commit_specifier: target commit specifier

    Returns:
        differences: List with strings/paths of changed/deleted files
    """
    response = None
    try:
        if not before_commit_specifier:
            response = client_codecommit.get_differences(
                repositoryName=repository_name,
                afterCommitSpecifier=after_commit_specifier,
            )
        else:
            response = client_codecommit.get_differences(
                repositoryName=repository_name,
                beforeCommitSpecifier=before_commit_specifier,
                afterCommitSpecifier=after_commit_specifier,
            )

    except Exception as e:
        logger.exception("Error getting CodeCommit differences: {}".format(e))
        raise e

    differences = []

    if response is None:
        return differences

    differences += response["differences"]
    while "nextToken" in response:
        try:
            if not before_commit_specifier:
                response = client_codecommit.get_differences(
                    repositoryName=repository_name,
                    afterCommitSpecifier=after_commit_specifier,
                    nextToken=response["nextToken"],
                )
            else:
                response = client_codecommit.get_differences(
                    repositoryName=repository_name,
                    beforeCommitSpecifier=before_commit_specifier,
                    afterCommitSpecifier=after_commit_specifier,
                    nextToken=response["nextToken"],
                )
            differences += response.get("differences", [])
        except Exception as e:
            logger.exception("Error getting CodeCommit differences: {}".format(e))
            raise e
    return differences


def get_previous_commit_id(repository_name, commit_id):
    """Get previous commit id.

    Args:
        repository_name: The repository name
        commit_id: Target CodeCommit commit ID

    Returns:
        previous_commit_id: Id of the last commit.
    """
    previous_commit_id = None
    try:
        response = client_codecommit.get_commit(
            repositoryName=repository_name, commitId=commit_id
        )
        commit = response["commit"]
        if len(commit["parents"]) > 0:
            previous_commit_id = commit["parents"][0]
    except Exception as e:
        logger.exception("Error getting CodeCommit Log: {}".format(e))
    return previous_commit_id


def get_changes_concatenated(differences_items, change_type):
    """Get changes concatenated into a comma separated string.

    Args:
        differences_items: Commit Difference
        change_type: type of change to filter [A,M,D]

    Returns:
        No return.
    """
    changes = ""
    try:
        filtered_changes = [
            diff for diff in differences_items if diff["changeType"] == change_type
        ]
        for diff in filtered_changes:
            if "afterBlob" in diff:
                path = diff["afterBlob"]["path"]
            else:
                path = diff["beforeBlob"]["path"]
            change_type = diff["changeType"]
            if changes == "":
                changes = path
            else:
                changes = "{0},{1}".format(changes, path)
        return changes
    except Exception as e:
        logger.exception(e)
        raise e


def get_changes(event, context, client=client_service_catalog):
    """Handle get changes request.

    Args:
        event: lambda event
        context: lambda context
        client: boto3 service client for Service Catalog

    Returns:
        No return.
    """
    logger.info("Evaluation of current Git changes ...")
    logger.info(event)
    logger.info(context)
    repository = REPOSITORY_NAME
    try:
        job_id = event["CodePipeline.job"]["id"]
        user_parameters = json.loads(
            event["CodePipeline.job"]["data"]["actionConfiguration"]["configuration"][
                "UserParameters"
            ]
        )
        logger.info(user_parameters)
        before_commit = user_parameters["before_commit"]
        after_commit = user_parameters["after_commit"]
    except Exception as e:
        logger.exception(e)
        raise e

    try:
        # attempt to resolve preious commit id in case before_commit is not specified
        if not before_commit:
            before_commit = get_previous_commit_id(repository, after_commit)
        logger.info(
            "Target commit: {}. Before commit: {}".format(after_commit, before_commit)
        )

        differences = get_file_changes(repository, before_commit, after_commit)

        added = get_changes_concatenated(differences, "A")
        if not added:
            added = "NoChanges"
        updated = get_changes_concatenated(differences, "M")
        if not updated:
            updated = "NoChanges"
        deleted = get_changes_concatenated(differences, "D")
        if not deleted:
            deleted = "NoChanges"

        logger.info("Files added: {}".format(added))
        logger.info("Files updated: {}".format(updated))
        logger.info("Files deleted: {}".format(deleted))

        output_vars = {
            "added_files": added,
            "modified_files": updated,
            "deleted_files": deleted,
            "job_id": job_id,
            "before_commit": before_commit,
            "after_commit": after_commit,
            "commit_id": after_commit,
        }

        put_job_success(
            codepipeline_client=client_codepipeline,
            job=job_id,
            output_variables=output_vars,
            message="Successfully identified changes ...",
        )
    except Exception as e:
        logger.exception(e)
        put_job_failure(
            codepipeline_client=client_codepipeline,
            job=job_id,
            message="Failure invoking Lambda action ... {}".format(e),
        )
        raise e
