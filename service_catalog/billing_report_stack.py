from aws_cdk import core

# from aws_cdk import aws_sns as _sns
# from aws_cdk import aws_s3 as _s3
# from aws_cdk import aws_iam as _iam
# from aws_cdk import aws_lambda as _lambda
# from aws_cdk import aws_events as _events
# from aws_cdk import aws_events_targets as _targets
from aws_cdk import aws_budgets as _budgets

from cdk_helper import Tags  # , Lambda, Rules, MetaData


class ReportStack(core.Stack):
    """Build the hd-billing-alerts-product."""

    def __init__(self, scope: core.Construct, id: str, branch: str, **kwargs) -> None:
        """Init the Construct fore creating hd-billing-alerts-product.

        Args:
            scope: CDK Parent Stack aap.py
            id: Name of the stack: "hd-billing-alerts-product"
            branch: feature, master or dmz unifier for seprated pipelines
            **kwargs:
        """
        super().__init__(scope, id, **kwargs)

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
            description="Billing alerts and reports via Lambda, Budgets, SNS and S3. So far the email is unformatted.",
            type="String",
            default="StandardMDPBillingApp",
        )

        # ===============================
        # Email
        email = core.CfnParameter(
            self,
            id="EmailDistributor",
            description="An email address. Best suited: HDI email distributor, because of the 10 subscription hard limit.",
            type="String",
            default="YOUR@EMAIL.COM",
        )

        emails_list = [email.value_as_string]

        # ===============================
        # Thresholds for Alerts in Budgets

        thresholds_list = [
            100,
            250,
            500,
            750,
            1000,
            1500,
            2000,
            3000,
            4000,
            5000,
        ]

        # ##############################################################
        # Budget Alert
        # ##############################################################

        subscribers_list = []

        for emails in emails_list:
            subscribers_list.append(
                _budgets.CfnBudget.SubscriberProperty(
                    address=emails, subscription_type="EMAIL"
                )
            )

        for thresholds in thresholds_list:
            property = _budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                budget_limit=_budgets.CfnBudget.SpendProperty(
                    amount=thresholds, unit="USD"
                ),
                time_unit="MONTHLY",
            )
            budgets = _budgets.CfnBudget(
                self,
                id="Budget-{}-{}".format(thresholds, branch),
                budget=property,
                notifications_with_subscribers=[
                    _budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=_budgets.CfnBudget.NotificationProperty(
                            comparison_operator="GREATER_THAN",
                            notification_type="ACTUAL",
                            threshold=80,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=subscribers_list,
                    )
                ],
            )

            tagging_list.append(budgets)

        # ##############################################################
        # Tag resources
        # ##############################################################

        Tags.tag_resources(
            resources_list=tagging_list,
            keys_list=["app"],
            values_list=[app_name.value_as_string],
        )
