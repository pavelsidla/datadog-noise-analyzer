terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    datadog = {
      source  = "DataDog/datadog"
      version = ">= 3.0"
    }
  }
}

provider "aws" {
  region = "eu-west-1"
}

provider "datadog" {
  # Credentials picked up from DD_API_KEY / DD_APP_KEY environment variables
  # or from the datadog_secret_arn secret in the module
}
