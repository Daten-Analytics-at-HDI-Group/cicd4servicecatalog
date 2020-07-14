from aws_cdk import core
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as _s3
from aws_cdk import aws_iam as _iam
from aws_cdk import aws_codecommit as _code
from aws_cdk import aws_codepipeline as _codepipeline
from aws_cdk import aws_codepipeline_actions as _codepipeline_actions
from aws_cdk import aws_codebuild as _codebuild
from aws_cdk import aws_servicecatalog as _servicecatalog
from aws_cdk import aws_ssm as _ssm

from cdk_helper import Tags, Lambda


class ServiceCatalogCICDStack(core.Stack):
    """hd-auto-service-catalog."""

    def __init__(
        self,
        scope: core.Construct,
        id: str,
        branch: str,
        sandbox_account: str,
        **kwargs
    ) -> None:
        """Init the Construct fore creating hd-auto-service-catalog.

        Args:
            scope: CDK Parent Stack aap.py
            id: Name of the stack: "hd-auto-service-catalog"
            branch: string for A/B Deployment
            sandbox_account: Sandbox account id
            **kwargs:
        """
        super().__init__(scope, id, **kwargs)

        # # The code that defines your stack goes here
        # def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
        #     string = "".join(random.choice(chars) for _ in range(size)).lower()
        #     return string
        #
        # branch = branch

        # ##############################################################
        # Tagging List
        # ##############################################################

        tagging_list = []

        # ##############################################################
        # Account List
        # ##############################################################

        # account_list = ["431892011317"]

        # ##############################################################
        # Parameters
        # ##############################################################

        # ===============================
        # App name
        app_name = core.CfnParameter(
            self,
            id="AppName-{}".format(branch),
            description="Name of the app",
            type="String",
            default="hd-auto-cicd-service-catalog",
        )

        # ===============================
        # Environment name
        env_name = core.CfnParameter(
            self,
            id="EnvName-{}".format(branch),
            description="Name of the environment",
            type="String",
            default="auto",
        )

        # ===============================
        # IAM Role and Policy parameter
        role_name = core.CfnParameter(
            self,
            id="ConstraintRoleName-{}".format(branch),
            description="Name of the launch constraint role",
            type="String",
            default="CrossAccountAdmin",
        )

        # ===============================
        # Principal management lambdas
        unassign_lambda = core.CfnParameter(
            self,
            id="UnassignPrincipalLambdaName-{}".format(branch),
            description="Name of the unassign principal management Lambda",
            type="String",
            default="UnassignPrincipalFromServiceCatalog",
        )

        assign_lambda = core.CfnParameter(
            self,
            id="AssignPrincipalLambdaName-{}".format(branch),
            description="Name of the assign principal management Lambda",
            type="String",
            default="AssignPrincipalToServiceCatalog",
        )

        # ===============================
        # Branch name
        if branch == "master":
            branch_name = "master"
        elif branch == "dmz":
            branch_name = "dmz"
        else:
            branch_name = "feature/{}".format(branch.split("-")[1])

        # ===============================
        # Path name
        path_name = core.CfnParameter(
            self,
            id="Path-{}".format(branch),
            description="CodeCommit repository folder for Service Catalogs Products",
            type="String",
            default="service_catalog/products/",
        )

        # ===============================
        # Path for the configuration INI
        path_ini = core.CfnParameter(
            self,
            id="ConfigINI-{}".format(branch),
            description="Configuration file path",
            type="String",
            default="service_catalog/config/config_{}.ini".format(branch.split("-")[0]),
        )

        # ===============================
        # Path for the template store
        template_store = core.CfnParameter(
            self,
            id="TemplateStore-{}".format(branch),
            description="S3 Bucket and Folder evaluated CloudFormation Templates",
            type="String",
            default="template-store/",
        )

        # ##############################################################
        # Artifacts Bucket
        # ##############################################################

        artifact_bucket = _s3.Bucket(
            self,
            id="ArtifactsBucket-{}".format(branch),
            bucket_name="my-sandbox-cicd-build-artifacts-{}".format(
                branch.split("-")[0]
            ),
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        empty_s3_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "s3:DeleteBucket",
                "s3:ListBucket",
                "s3:DeleteObjects",
                "s3:DeleteObject",
            ],
            resources=[artifact_bucket.bucket_arn, artifact_bucket.bucket_arn + "/*",],
        )

        empty_bucket_lambda = Lambda.create_lambda(
            self,
            name="EmptyArtifactsBucket-{}".format(branch),
            function_name="EmptyArtifactsBucket-{}".format(branch),
            handler="empty_bucket.empty_bucket",
            code_injection_method=_lambda.Code.asset(path="./src/lambda/empty_bucket/"),
            lambda_runtime=_lambda.Runtime.PYTHON_3_7,
            amount_of_memory=128,
            timeout=30,
            amount_of_retries=0,
            rules_to_invoke=None,
            events_to_invoke=None,
            lambda_layers_to_use=None,
            policy_statements=[empty_s3_policy,],
            log_retention=None,
            environment_vars=[],
        )

        cr_empty_bucket = core.CustomResource(
            self,
            id="CR-EmptyBucket-{}".format(branch),
            service_token=empty_bucket_lambda.lambda_function_object.function_arn,
            properties={"BUCKET_NAME": artifact_bucket.bucket_name,},
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        cr_empty_bucket.node.add_dependency(artifact_bucket)

        tagging_list.append(cr_empty_bucket)

        artifact_bucket.add_to_resource_policy(
            permission=_iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["s3:GetObject"],
                resources=[artifact_bucket.bucket_arn + "/template-store/*",],
                principals=[_iam.ServicePrincipal("servicecatalog"),],
            )
        )

        tagging_list.append(artifact_bucket)

        # ##############################################################
        # Code repo
        # ##############################################################

        if branch == "master":
            service_catalog_git = _code.Repository(
                self,
                id="ServiceCatalogGit",
                repository_name="hd-auto-service-catalog",
                description="This git hosts all templates for the ServiceCatalog and the CICD itself.",
            )
            tagging_list.append(service_catalog_git)
        else:
            service_catalog_git = _code.Repository.from_repository_name(
                self, id="ServiceCatalogGit", repository_name="hd-auto-service-catalog",
            )
            tagging_list.append(service_catalog_git)

        # ##############################################################
        # Lambda Layer
        # ##############################################################

        source_code = _lambda.Code.from_asset("./src/lambda_layer/")

        layer = _lambda.LayerVersion(
            self,
            id="Python3_7_Layer-{}".format(branch),
            code=source_code,
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_7],
        )

        tagging_list.append(layer)

        # ##############################################################
        # CodeBuild Project
        # ##############################################################

        build_project = _codebuild.PipelineProject(
            self,
            id="BuildProject-{}".format(branch),
            project_name="hd-auto-cicd-service-catalog-{}".format(branch),
            description="Build project for the Service Catalog pipeline",
            environment=_codebuild.BuildEnvironment(
                build_image=_codebuild.LinuxBuildImage.STANDARD_4_0, privileged=True
            ),
            cache=_codebuild.Cache.bucket(artifact_bucket, prefix="codebuild-cache"),
            build_spec=_codebuild.BuildSpec.from_source_filename("./buildspec.yaml"),
        )

        tagging_list.append(build_project)

        # CodeBuild IAM permissions to read write to s3
        artifact_bucket.grant_read_write(build_project)
        # Build and create test runs for templates
        build_project.add_to_role_policy(
            statement=_iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                not_actions=["aws-portal:*", "organizations:*"],
                resources=["*"],  # No further restriction due to IAM!
            )
        )

        # ##############################################################
        # Service Catalog
        # ##############################################################

        portfolio = _servicecatalog.CfnPortfolio(
            self,
            id="BasicPortfolio-{}".format(branch),
            display_name="hd-mdp-portfolio-{}".format(branch),
            provider_name="MDP-Team",
            accept_language="en",
            description="""
                This portfolio contains AWS Services combined into technical and functional approved architectures.
                You don't need IAM permissions to run those products. You will use them.
                """,
        )

        remove_portfolio_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "servicecatalog:SearchProductsAsAdmin",
                "servicecatalog:DeleteProduct",
                "servicecatalog:DeleteConstraint",
                "servicecatalog:ListConstraintsForPortfolio",
                "servicecatalog:DisassociatePrincipalFromPortfolio",
                "servicecatalog:DisassociateProductFromPortfolio",
            ],
            resources=["*",],
        )

        iam_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "iam:GetRole",
                "iam:PassRole",
                "iam:CreateRole",
                "iam:DeleteRole",
                "iam:ListRoles",
                "iam:PutRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:DeletePolicy",
            ],
            resources=[
                "arn:aws:iam::{}:role/{}".format(
                    core.Aws.ACCOUNT_ID, role_name.value_as_string
                ),
            ],
        )

        remove_products_lambda = Lambda.create_lambda(
            self,
            name="RemoveProductsFromPortfolio-{}".format(branch),
            function_name="RemoveProductsFromPortfolio-{}".format(branch),
            handler="remove_portfolio.remove_portfolio",
            code_injection_method=_lambda.Code.asset(
                path="./src/lambda/remove_portfolio/"
            ),
            lambda_runtime=_lambda.Runtime.PYTHON_3_7,
            amount_of_memory=128,
            timeout=30,
            amount_of_retries=0,
            rules_to_invoke=None,
            events_to_invoke=None,
            lambda_layers_to_use=None,
            policy_statements=[remove_portfolio_policy, iam_policy],
            log_retention=None,
            environment_vars=[
                {"Key": "SANDBOX_ACCOUNT_ID", "Value": "{}".format(sandbox_account),}
            ],
        )

        cr_remove_products = core.CustomResource(
            self,
            id="CR-RemoveProductsFromPortfolio-{}".format(branch),
            service_token=remove_products_lambda.lambda_function_object.function_arn,
            properties={"PORTFOLIO_ID": portfolio.ref,},
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        cr_remove_products.node.add_dependency(portfolio)

        iam_role_list = [role_name.value_as_string]
        if branch == "master":
            # TODO: Accept Portfolio share principal management
            #     for idx, account in enumerate(account_list):
            #         _servicecatalog.CfnPortfolioShare(
            #             self,
            #             id="PortfolioSharing-{}-{}".format(branch, idx),
            #             account_id=account,
            #             portfolio_id=portfolio.ref,
            #             accept_language="en",
            #         )
            for idx, role in enumerate(iam_role_list):
                _servicecatalog.CfnPortfolioPrincipalAssociation(
                    self,
                    id="PrincipalAssociation-{}-{}".format(branch, idx),
                    portfolio_id=portfolio.ref,
                    principal_arn="arn:aws:iam::{}:role/{}".format(
                        core.Aws.ACCOUNT_ID, role
                    ),
                    principal_type="IAM",
                    accept_language="en",
                )
            core.CfnOutput(
                self, id="PortfolioId-{}".format(branch), value=portfolio.ref
            )
            tagging_list.append(portfolio)
        else:
            for idx, role in enumerate(iam_role_list):
                _servicecatalog.CfnPortfolioPrincipalAssociation(
                    self,
                    id="PrincipalAssociation-{}-{}".format(branch, idx),
                    portfolio_id=portfolio.ref,
                    principal_arn="arn:aws:iam::{}:role/{}".format(
                        core.Aws.ACCOUNT_ID, role
                    ),
                    principal_type="IAM",
                    accept_language="en",
                )
            core.CfnOutput(
                self, id="PortfolioId-{}".format(branch), value=portfolio.ref
            )
            tagging_list.append(portfolio)

        # ##############################################################
        # Lambda Permissions
        # ##############################################################

        s3_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "s3:GetObject*",
                "s3:GetBucket*",
                "s3:List*",
                "s3:DeleteObject*",
                "s3:PutObject*",
                "s3:Abort*",
            ],
            resources=[artifact_bucket.bucket_arn, artifact_bucket.bucket_arn + "/*"],
        )

        codecommit_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "codecommit:GetDifferences",
                "codecommit:GetBranch",
                "codecommit:GetCommit",
            ],
            resources=[service_catalog_git.repository_arn],
            conditions={"StringEquals": {"aws:RequestedRegion": "eu-central-1"}},
        )

        codebuild_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=["codebuild:StartBuild", "codebuild:UpdateProject*"],
            resources=[build_project.project_arn],
            conditions={"StringEquals": {"aws:RequestedRegion": "eu-central-1"}},
        )

        service_catalog_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "servicecatalog:CreateProduct",
                "servicecatalog:CreateProvisioningArtifact",
                "servicecatalog:UpdateProvisioningArtifact",
                "servicecatalog:DeleteProvisioningArtifact",
                "servicecatalog:ListProvisioningArtifacts",
                "servicecatalog:ListPortfolios",
                "servicecatalog:SearchProductsAsAdmin",
                "servicecatalog:AssociateProductWithPortfolio",
                "servicecatalog:AssociatePrincipalWithPortfolio",
                "servicecatalog:DisassociatePrincipalFromPortfolio",
                "servicecatalog:DisassociateProductFromPortfolio",
                "servicecatalog:DeleteProduct",
                "servicecatalog:CreatePortfolioShare",
                "servicecatalog:AcceptPortfolioShare",
                "servicecatalog:CreateConstraint",
                "servicecatalog:DeleteConstraint",
                "servicecatalog:ListConstraintsForPortfolio",
            ],
            resources=["*"],
        )

        sts_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=["sts:AssumeRole"],
            resources=[
                "arn:aws:iam::{}:role/{}".format(
                    sandbox_account, role_name.value_as_string
                ),
            ],
        )

        codepipeline_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "codepipeline:PutJobFailureResult",  # Supports only a wildcard (*) in the policy Resource element.
                "codepipeline:PutJobSuccessResult",  # Supports only a wildcard (*) in the policy Resource element.
            ],  # https://docs.aws.amazon.com/codepipeline/latest/userguide/permissions-reference.html
            resources=["*"],
            conditions={"StringEquals": {"aws:RequestedRegion": "eu-central-1"}},
        )

        lambda_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "lambda:GetFunction",
                "lambda:CreateFunction",
                "lambda:DeleteFunction",
                "lambda:AddPermission",
                "lambda:RemovePermission",
                "lambda:CreateEventSourceMapping",
                "lambda:DeleteEventSourceMapping",
                "lambda:InvokeFunction",
                "lambda:UpdateFunctionCode",
                "lambda:UpdateFunctionConfiguration",
            ],
            resources=[
                "arn:aws:lambda:{}:{}:function:{}-{}".format(
                    core.Aws.REGION,
                    sandbox_account,
                    unassign_lambda.value_as_string,
                    sandbox_account,
                ),
                "arn:aws:lambda:{}:{}:function:{}-{}".format(
                    core.Aws.REGION,
                    sandbox_account,
                    assign_lambda.value_as_string,
                    sandbox_account,
                ),
            ],
            conditions={"StringEquals": {"aws:RequestedRegion": "eu-central-1"}},
        )

        # ##############################################################
        # CICD Lambdas
        # ##############################################################

        # ==========================
        # Get Latest Git Meta Data
        git_metadata = Lambda.create_lambda(
            self,
            name="GetLastGitChanges-{}".format(branch),
            function_name="GetLastGitChanges-{}".format(branch,),
            handler="git_metadata.get_changes",
            code_injection_method=_lambda.Code.asset(path="./src/lambda/git_metadata/"),
            lambda_runtime=_lambda.Runtime.PYTHON_3_7,
            amount_of_memory=128,
            timeout=30,
            amount_of_retries=0,
            rules_to_invoke=None,
            events_to_invoke=None,
            lambda_layers_to_use=[layer],
            policy_statements=[
                codecommit_policy,
                codebuild_policy,
                codepipeline_policy,
                service_catalog_policy,
            ],
            log_retention=None,
            environment_vars=[
                {
                    "Key": "REPOSITORY_NAME",
                    "Value": "{}".format(service_catalog_git.repository_name),
                },
            ],
        )

        # ==========================
        # Principal Management Lambda
        principal_management = Lambda.create_lambda(
            self,
            name="PrincipalManagement-{}".format(branch),
            function_name="PrincipalManagement-{}".format(branch),
            handler="principal_management.principal_management",
            code_injection_method=_lambda.Code.asset(
                path="./src/lambda/principal_management/"
            ),
            lambda_runtime=_lambda.Runtime.PYTHON_3_7,
            amount_of_memory=1024,
            timeout=120,
            amount_of_retries=0,
            rules_to_invoke=None,
            events_to_invoke=None,
            lambda_layers_to_use=[layer],
            policy_statements=[
                iam_policy,
                lambda_policy,
                sts_policy,
                service_catalog_policy,
                codepipeline_policy,
                codecommit_policy,
            ],
            log_retention=None,
            environment_vars=[
                {"Key": "SANDBOX_ACCOUNT_ID", "Value": "{}".format(sandbox_account),}
            ],
        )

        # ==========================
        # Sync Service Catalog Lambda

        service_catalog_synchronisation = Lambda.create_lambda(
            self,
            name="UpdateServiceCatalog-{}".format(branch),
            function_name="UpdateServiceCatalog-{}".format(branch),
            handler="sync_catalog.service_catalog_janitor",
            code_injection_method=_lambda.Code.asset(
                path="./src/lambda/update_servicecatalog/"
            ),
            lambda_runtime=_lambda.Runtime.PYTHON_3_7,
            amount_of_memory=1024,
            timeout=120,
            amount_of_retries=0,
            rules_to_invoke=None,
            events_to_invoke=None,
            lambda_layers_to_use=[layer],
            policy_statements=[
                sts_policy,
                service_catalog_policy,
                codepipeline_policy,
                codecommit_policy,
                iam_policy,
                s3_policy,
            ],
            log_retention=None,
            environment_vars=[
                {
                    "Key": "LOCAL_ROLE_NAME_SC",
                    "Value": "{}".format(role_name.value_as_string),
                },
                {"Key": "SANDBOX_ACCOUNT_ID", "Value": "{}".format(sandbox_account),},
                {
                    "Key": "REPOSITORY_NAME",
                    "Value": "{}".format(service_catalog_git.repository_name),
                },
                {"Key": "PATH_INI", "Value": "{}".format(path_ini.value_as_string)},
                {"Key": "PATH", "Value": "{}".format(path_name.value_as_string)},
                {"Key": "BUCKET", "Value": "{}".format(artifact_bucket.bucket_name)},
                {
                    "Key": "S3_PATH",
                    "Value": "{}".format(template_store.value_as_string),
                },
            ],
        )

        # ##############################################################
        # CodePipeline
        # ##############################################################

        # General output
        source_output = _codepipeline.Artifact("git-change")
        tested_source_files = _codepipeline.Artifact("tested-cfn")

        cicd_pipeline = _codepipeline.Pipeline(
            self,
            id="ServiceCatalogPipeline-{}".format(branch),
            pipeline_name="ServiceCatalog-CICD-{}".format(branch),
            artifact_bucket=artifact_bucket,
            stages=[
                _codepipeline.StageProps(
                    stage_name="Source_CFN-Templates",
                    actions=[
                        _codepipeline_actions.CodeCommitSourceAction(
                            action_name="SourceControlCFNTemplates",
                            output=source_output,
                            repository=service_catalog_git,
                            variables_namespace="source",
                            branch=branch_name,
                        ),
                    ],
                ),
                _codepipeline.StageProps(
                    stage_name="Getting_CFN-Template",
                    actions=[
                        _codepipeline_actions.LambdaInvokeAction(
                            action_name="GettingCFNTemplate",
                            lambda_=git_metadata.lambda_function_object,
                            user_parameters={
                                "before_commit": "",
                                "after_commit": "#{source.CommitId}",
                            },
                            variables_namespace="filtered_source",
                        )
                    ],
                ),
                _codepipeline.StageProps(
                    stage_name="Testing_CFN-Template",
                    actions=[
                        _codepipeline_actions.CodeBuildAction(
                            type=_codepipeline_actions.CodeBuildActionType.BUILD,
                            action_name="TestingCFNTemplates",
                            project=build_project,
                            input=source_output,
                            outputs=[tested_source_files],
                            environment_variables={
                                "PIPELINE_NAME": _codebuild.BuildEnvironmentVariable(
                                    value="ServiceCatalog-CICD-{}".format(branch),
                                    type=_codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                                ),
                                "FILES_ADDED": _codebuild.BuildEnvironmentVariable(
                                    value="#{filtered_source.added_files}",
                                    type=_codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                                ),
                                "FILES_MODIFIED": _codebuild.BuildEnvironmentVariable(
                                    value="#{filtered_source.modified_files}",
                                    type=_codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                                ),
                                "FILES_DELETED": _codebuild.BuildEnvironmentVariable(
                                    value="#{filtered_source.deleted_files}",
                                    type=_codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                                ),
                                "JOB_ID": _codebuild.BuildEnvironmentVariable(
                                    value="#{filtered_source.job_id}",
                                    type=_codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                                ),
                                "REPOSITORY_BRANCH": _codebuild.BuildEnvironmentVariable(
                                    value="#{source.BranchName}",
                                    type=_codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                                ),
                                "REPOSITORY_NAME": _codebuild.BuildEnvironmentVariable(
                                    value="#{source.RepositoryName}",
                                    type=_codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                                ),
                            },
                        )
                    ],
                ),
                _codepipeline.StageProps(
                    stage_name="Principal_Management",
                    actions=[
                        _codepipeline_actions.LambdaInvokeAction(
                            action_name="PrincipalManagement",
                            lambda_=principal_management.lambda_function_object,
                            user_parameters={
                                "job_id": "#{filtered_source.job_id}",
                                "commit_id": "#{filtered_source.commit_id}",
                                "portfolio_id": portfolio.ref,
                            },
                        )
                    ],
                ),
                _codepipeline.StageProps(
                    stage_name="Update_Servicecatalog",
                    actions=[
                        _codepipeline_actions.LambdaInvokeAction(
                            action_name="UpdateServiceCatalog",
                            lambda_=service_catalog_synchronisation.lambda_function_object,
                            inputs=[source_output],
                            user_parameters={
                                "modified_files": "#{filtered_source.modified_files}",
                                "added_files": "#{filtered_source.added_files}",
                                "deleted_files": "#{filtered_source.deleted_files}",
                                "job_id": "#{filtered_source.job_id}",
                                "commit_id": "#{filtered_source.commit_id}",
                                "portfolio_id": portfolio.ref,
                            },
                        )
                    ],
                ),
            ],
        )

        cicd_pipeline.add_to_role_policy(
            statement=_iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["codecommit:GetBranch", "codecommit:GetCommit"],
                resources=[service_catalog_git.repository_arn],
            )
        )

        tagging_list.append(cicd_pipeline)

        # ##############################################################
        # Tag resources
        # ##############################################################

        Tags.tag_resources(
            resources_list=tagging_list,
            keys_list=["app", "env"],
            values_list=[app_name.value_as_string, env_name.value_as_string],
        )

        _ssm.StringParameter(
            self,
            id="LambdaLayerExport-{}".format(branch),
            parameter_name="/hd/mdp/{}/lambda/layer-pandas-numpy-servicecatalog".format(
                branch
            ),
            description="Lambda Layer ARN",
            string_value=layer.layer_version_arn,
        )
