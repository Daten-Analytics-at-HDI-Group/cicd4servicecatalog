from aws_cdk import core

# from aws_cdk import aws_servicecatalog as _servicecatalog
from aws_cdk import aws_lambda as _lambda
from cdk_helper import Tags
from aws_cdk import aws_ssm as _ssm


class ServiceCatalogCICDDependency(core.Stack):
    """hd-auto-service-catalog dependencies."""

    def __init__(
        self,
        scope: core.Construct,
        id: str,
        branch: str,
        portfolio_id: str,
        dev_account: str,
        auto_account: str,
        uat_account: str,
        prod_account,
        env: str,
        **kwargs
    ) -> None:
        """Init the Construct fore creating hd-auto-service-catalog dependencies.

        Args:
            scope: CDK Parent Stack aap.py
            id: Name of the stack: "hd-auto-service-catalog"
            branch: string for A/B Deployment,
            portfolio_id: ID of the Service catalog portfolio
            env: Account type within MDP,
            dev_account: Dev account id
            uat_account: UAT account id
            prod_account: Prod account id
            auto_account: Auto account id
            **kwargs:
        """
        super().__init__(scope, id, **kwargs)

        # ##############################################################
        # Tagging List
        # ##############################################################

        tagging_list = []

        ###############################################################
        # Parameters
        # ##############################################################

        # ===============================
        # App name
        app_name = core.CfnParameter(
            self,
            id="AppName",
            description="Name of the app",
            type="String",
            default="hd-sc-dependencies",
        )

        # ===============================
        # Environment name
        env_name = core.CfnParameter(
            self,
            id="EnvName",
            description="Name of the environment",
            type="String",
            default="auto",
        )

        # ##############################################################
        # Lambda Layer
        # ##############################################################

        source_code = _lambda.Code.from_asset(
            "./src/lambda_layer/",  # bundling=bundling_options
        )

        layer = _lambda.LayerVersion(
            self,
            id="Python3_7_Layer-{}".format(branch),
            code=source_code,
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_7],
        )

        tagging_list.append(layer)

        _ssm.StringParameter(
            self,
            id="LambdaLayer-{}".format(branch),
            parameter_name="/hd/mdp/{}/lambda/layer-pandas-numpy-servicecatalog".format(
                branch
            ),
            description="Lambda Layer ARN",
            string_value=layer.layer_version_arn,
        )

        # ##############################################################
        # Principal Assignment
        # ##############################################################

        # TODO: Accept Portfolio share principal management
        # iam_role_list = [
        #     "CrossAccountSuperAdmin"
        # ]
        # acceptation = _servicecatalog.CfnAcceptedPortfolioShare(
        #     self,
        #     id="PortfolioShare-{}".format(branch),
        #     portfolio_id=portfolio_id,
        #     accept_language="en",
        # )
        # for idx, role in enumerate(iam_role_list):
        #     association = _servicecatalog.CfnPortfolioPrincipalAssociation(
        #         self,
        #         id="PrincipalAssociation-{}-{}".format(branch, idx),
        #         portfolio_id=portfolio_id,
        #         principal_arn="arn:aws:iam::{}:role/{}".format(
        #             core.Aws.ACCOUNT_ID, role
        #         ),
        #         principal_type="IAM",
        #         accept_language="en",
        #     )
        #     association.node.add_dependency(acceptation)

        # ##############################################################
        # Tag resources
        # ##############################################################

        Tags.tag_resources(
            resources_list=tagging_list,
            keys_list=["app", "env"],
            values_list=[app_name.value_as_string, env_name.value_as_string],
        )
