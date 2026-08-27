terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }


  backend "s3" {
    bucket         = "gha-test-repo-terraform-state"
    key            = "gha-test-repo/terraform.tfstate"
    region         = "us-east-2"
    dynamodb_table = "gha-test-repo-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = "us-east-2"
}