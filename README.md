
# CICD Pipeline for HDI Service Catalog

## Description

* This repo contains a CDK app for the CICD pipeline.
* Every product for the Service Catalog will be an additional part of this app.

## Purpose

* Deploying AWS Infrastructure without IAM Permissions.
* Prodviding tested and deployable AWS Infrastructure CloudFormation Templates.
* Delete deprecated products and product versions.

## Architecture

![Architecture](./architecture.png)

## Getting started

* This is a `Python CDK App`:
    * `source .env/bin/activate`
    * `pip install git-remote-codecommit`
* Now, you can use `git clone codecommit::eu-central-1://hd-auto-service-catalog`
* Finally, run `pip install -r requirements.txt`

## Usage

* Create your new `stack.py` under `service_catalog`. 
* Configure `app.py` accordingly:

```python
from aws_cdk import core
from service_catalog.service_catalog_cicd_stack import ServiceCatalogCICDStack
from service_catalog.custom_vpc import CustomVpcStack
# Added service
from service_catalog.YOUR_STACK_HERE import YOUR_CLASS_HERE

app = core.App()

ServiceCatalogCICDStack(app, "hd-auto-service-catalog")
CustomVpcStack(app, "custom-vpc")
# Added service
YOUR_CLASS_HERE(app, YOUR_STACK_NAME)

app.synth()
```

* Run `cdk synth "YOUR_STACK_NAME" > service_catalog/products/*.yaml`

## Configuration

* Enhence `service_catalog/config/config.ini` accordingly to your product. Choose a human friendly name for the product! The section name and 
* All fields in `config.ini` are necessary.
* To deprecate a product, delete the corresponding section within `config.ini`. The deletion takes place, while a new product or an updated version of existing product will be pushed.

## Restrictions

* Only the master branch will be used for the CICD pipeline.
* So far, only the latest version of the product will be provided throuigh the `Service Catalog`.
* You can use `"\\*_{}[]()>#+-.!$/"` within your `FILE_NAME`. For comparision, all these special characters will be replaced.
* The same applies to `Name` and `Section ([foo_bar.yaml])` within `service_catalog/config/config.ini`. But you need to take the same letters in the same order for both parameters.
* If you need assets, you need to add those assets within `service_catalog_cicd_stack.py`.
* So far, the deployment of multiple *.yaml-files at once is not supported. Also, a commit with a deletion and a new/updated *.yaml-file will not work. We are working on this ...

```yaml
[custom_vpc.yaml]
...
Name: CustomVPC or Custom_VPC or Custom-VPC or customvpc # does not matter
...
```

## Inspiration of this project

* AWS Blogpostfrom 2017: https://aws.amazon.com/blogs/devops/aws-service-catalog-sync-code/
* And its Repo: https://github.com/aws-samples/aws-pipeline-to-service-catalog
