#!/usr/bin/env python3

from aws_cdk import core

from service_catalog.products.service_catalog_cicd_stack import ServiceCatalogCICDStack
from service_catalog.products.service_catalog_cicd_dependency import (
    ServiceCatalogCICDDependency,
)
from service_catalog.products.billing_report_stack import ReportStack
from service_catalog.products.sagemaker_with_git import SagemakerDevGit

# ===============================
# MDP Account IDs

sandbox_account_id = "800524020870"

app = core.App()

# ##############################################################
# Branching concept on Changes of the CICD or the Service Catalog
# ##############################################################

# TODO: Changes feature/name_of_feature accordingly
branches = ["master", "dmz", "feature-improveS3security"]

for branch in branches:
    ServiceCatalogCICDStack(
        app,
        "hd-auto-service-catalog-{}".format(branch),
        branch=branch,
        sandbox_account=sandbox_account_id,
    )

PORTFOLIO_ID_MASTER = "port-2hlps2tljtefa"
PORTFOLIO_ID_DMZ = "port-f3a2s5istcfuy"
PORTFOLIO_ID_FEATURE = ""

portfolio_ids = [PORTFOLIO_ID_MASTER, PORTFOLIO_ID_DMZ, PORTFOLIO_ID_FEATURE]

for env in environments:
    for branch, portfolio_id in zip(branches, portfolio_ids):
        ServiceCatalogCICDDependency(
            app,
            "hd-{}-service-catalog-dependency-{}".format(env, branch),
            branch=branch,
            portfolio_id=portfolio_id,
            env=env,
            dev_account=dev_account_id,
            uat_account=uat_account_id,
            prod_account=prod_account_id,
            auto_account=auto_account_id,
        )

# ##############################################################
# Branching concept for Products
# ##############################################################

product_branch = "feauture"

ReportStack(
    app, "hd-billing-alerts-product-{}".format(product_branch), branch=product_branch
)

SagemakerDevGit(
    app, "hd-datascience-product-git-{}".format(product_branch), branch=product_branch
)

app.synth()
