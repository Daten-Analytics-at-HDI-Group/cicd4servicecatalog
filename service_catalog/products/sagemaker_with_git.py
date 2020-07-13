from aws_cdk import core
from aws_cdk import aws_sagemaker as _sagemaker
from aws_cdk import aws_iam as _iam
from aws_cdk import aws_s3 as _s3
from aws_cdk import aws_codecommit as _git

# #TODO: Add KMS
# from aws_cdk import aws_kms as _kms

import string
import random

from cdk_helper import Tags, MetaData


class SagemakerDevGit(core.Stack):
    """Build the hd-datascience-product."""

    def __init__(self, scope: core.Construct, id: str, branch: str, **kwargs) -> None:
        """Init the Construct fore creating hd-datascience-product.

        Args:
            scope: CDK Parent Stack aap.py
            id: Name of the stack: "hd-datascience-product"
            branch: feature, master or dmz unifier for seprated pipelines
            **kwargs:
        """
        super().__init__(scope, id, **kwargs)

        # The code that defines your stack goes here
        def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
            string = "".join(random.choice(chars) for _ in range(size)).lower()
            return string

        # ##############################################################
        # Tagging List
        # ##############################################################

        tagging_list = []

        # ##############################################################
        # Parameters
        # ##############################################################

        # ===============================
        # App name
        app_name = core.CfnParameter(
            self,
            id="AppName",
            description="Name of the app",
            type="String",
            default="hd-datascience-product",
        )

        # ===============================
        # HDI Personal  Number
        hdi_personal_id = core.CfnParameter(
            self,
            id="HDIPersonalID",
            description="Enter your HDI personal ID",
            type="String",
            default="123456",
        )

        # ===============================
        # Bucket Name
        bucket_name_id = core.CfnParameter(
            self,
            id="BucketName",
            description="""
            Enter your bucket name plus a random hash.
            Additionally you HDI Personal
            ID will be added to the bucket name.
            The bucket name needs to be unique and DNS compliant.
            """,
            type="String",
            default="hd-datascience-{}".format(id_generator()),
        )

        # ===============================
        # Repo Name
        repo_name = core.CfnParameter(
            self,
            id="RepositoryName",
            description="""
            Enter the exact name of of your existing
            CodeCommit repository
            """,
            type="String",
            default="hd-test-git-datascience-{}".format(id_generator()),
        )

        # ===============================
        # Instance type
        instance_type = core.CfnParameter(
            self,
            id="SagemakerInstanceTypeString",
            description="""
            Enter a Sagemaker instance identifier.
            Theses identifier starts with 'ml.'
            """,
            type="String",
            default="ml.t2.medium",
        )

        # #######################
        # S3 Bucket
        # #######################

        bucket = _s3.Bucket(
            self,
            id="DataS3Bucket-{}".format(branch),
            bucket_name=bucket_name_id.value_as_string
            + "-"
            + hdi_personal_id.value_as_string,
            removal_policy=core.RemovalPolicy.DESTROY,
            block_public_access=_s3.BlockPublicAccess.BLOCK_ALL,
            # TODO: First Add Bucket Encryption
            # encryption=_s3.BucketEncryption.KMS_MANAGED,
        )

        # TODO: First Add Bucket Policy
        # bucket_pol = _iam.PolicyStatement(
        #     effect=_iam.Effect.ALLOW,
        #     actions=[
        #         "s3:GetObject*",
        #         "s3:GetBucket*",
        #         "s3:List*",
        #         "s3:DeleteObject*",
        #         "s3:PutObject*",
        #         "s3:Abort*",
        #     ],
        #     principals=[_iam.ServicePrincipal(service="sagemaker.amazonaws.com")],
        #     resources=[bucket.bucket_arn, bucket.bucket_arn + "/*"],
        # )

        # bucket.add_to_resource_policy(bucket_pol)

        # TODO: Add Metadata to suppres warning
        # MetaData.add_metadata_to_cfn_object(
        #     cdk_construct=bucket,
        #     json_object={
        #         "cfn_nag": {
        #             "rules_to_suppress": [
        #                 {
        #                     "id": "W35",
        #                     "reason": "So far, we do not log every private bucket.",
        #                 }
        #             ]
        #         }
        #     },
        # )

        tagging_list.append(bucket)

        # #######################
        # CodeCommit
        # #######################

        repository = _git.Repository(
            self,
            id="CodeRepository",
            repository_name=repo_name.value_as_string,
            description="This repo holds your code",
        )

        tagging_list.append(repository)

        # #######################
        # IAM Roles
        # #######################

        sagemaker_notebook_role = _iam.Role(
            self,
            id="SagemakerNotebookRole-{}".format(branch),
            assumed_by=_iam.ServicePrincipal("sagemaker"),
            role_name="hd-mdp-role-for-sagermaker-{}".format(
                hdi_personal_id.value_as_string
            ),
            managed_policies=[
                _iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    id="DataScienceProduct",
                    managed_policy_arn="arn:aws:iam::aws:policy/AmazonSageMakerFullAccess",
                )
            ],
        )

        MetaData.add_metadata_to_cfn_object(
            cdk_construct=sagemaker_notebook_role,
            json_object={
                "cfn_nag": {
                    "rules_to_suppress": [
                        {
                            "id": "W28",
                            "reason": "There is no direct update on existing stacks where this matters",
                        }
                    ]
                }
            },
        )

        # #######################
        # Sagemaker
        # #######################

        # TODO: First Add KMS
        # kms_key = _kms.Key(
        #     self,
        #     id="KMSKeyForSagemaker-{}".format(branch),
        #     enabled=True,
        #     enable_key_rotation=True,
        #     removal_policy=core.RemovalPolicy.DESTROY,
        # )

        git_property = _sagemaker.CfnCodeRepository.GitConfigProperty(
            repository_url=repository.repository_clone_url_http
        )

        git = _sagemaker.CfnCodeRepository(
            self,
            id="SagemakerGitDataScience-{}".format(branch),
            code_repository_name=repo_name.value_as_string
            + "-"
            + hdi_personal_id.value_as_string,
            git_config=git_property,
        )

        tagging_list.append(git)

        with open("./src/lifecycle_configurations/auto_stop.sh", "r") as auto_stop:
            auto_stop_config = auto_stop.read()

        config = _sagemaker.CfnNotebookInstanceLifecycleConfig(
            self,
            id="LifeCycleConfig-{}".format(branch),
            notebook_instance_lifecycle_config_name=core.Fn.join(
                delimiter="-",
                list_of_values=[
                    app_name.value_as_string,
                    hdi_personal_id.value_as_string,
                ],
            ),
            on_start=[{"content": core.Fn.base64(auto_stop_config)}],
            on_create=[{"content": core.Fn.base64(auto_stop_config)}],
        )

        tagging_list.append(config)

        notebook = _sagemaker.CfnNotebookInstance(
            self,
            id="SagemakerInstance-{}".format(branch),
            instance_type=instance_type.value_as_string,
            default_code_repository=repository.repository_clone_url_http,
            notebook_instance_name=core.Fn.join(
                delimiter="-",
                list_of_values=[
                    app_name.value_as_string,
                    hdi_personal_id.value_as_string,
                ],
            ),
            lifecycle_config_name=config.attr_notebook_instance_lifecycle_config_name,
            role_arn=sagemaker_notebook_role.role_arn,
            # TODO: First Add KMS
            # kms_key_id=ksm_key.key_id,
        )

        tagging_list.append(notebook)

        sagemaker_notebook_policy = _iam.Policy(
            self,
            id="SagemakerNotebookRolePolicy-{}".format(branch),
            policy_name="hd-policy-for-sagermaker-notebook-{}".format(
                hdi_personal_id.value_as_string
            ),
            statements=[
                _iam.PolicyStatement(
                    effect=_iam.Effect.ALLOW,
                    actions=[
                        "codecommit:BatchAssociateApprovalRuleTemplateWithRepositories",
                        "codecommit:BatchDisassociateApprovalRuleTemplateFromRepositories",
                        "codecommit:BatchGet*",
                        "codecommit:BatchDescribe*",
                        "codecommit:Create*",
                        "codecommit:DeleteBranch",
                        "codecommit:DeleteFile",
                        "codecommit:Describe*",
                        "codecommit:DisassociateApprovalRuleTemplateFromRepository",
                        "codecommit:EvaluatePullRequestApprovalRules",
                        "codecommit:Get*",
                        "codecommit:List*",
                        "codecommit:Merge*",
                        "codecommit:OverridePullRequestApprovalRules",
                        "codecommit:Put*",
                        "codecommit:Post*",
                        "codecommit:TagResource",
                        "codecommit:Test*",
                        "codecommit:UntagResource",
                        "codecommit:Update*",
                        "codecommit:GitPull",
                        "codecommit:GitPush",
                    ],
                    resources=[repository.repository_arn],
                ),
                _iam.PolicyStatement(
                    effect=_iam.Effect.ALLOW,
                    actions=["s3:List*", "s3:Get*", "s3:Put*", "s3:Describe*",],
                    resources=[bucket.bucket_arn],
                ),
            ],
        )

        sagemaker_notebook_policy.attach_to_role(sagemaker_notebook_role)

        # ##############################################################
        # Tag resources
        # ##############################################################

        Tags.tag_resources(
            resources_list=tagging_list,
            keys_list=["app"],
            values_list=[app_name.value_as_string],
        )
