resource "aws_default_vpc" "default" {
    tags = {
      Name = "Default-Do-Not-Delete"
    }
}

resource "aws_default_subnet" "use2a" {
  availability_zone = "us-east-2a"
}

resource "aws_default_subnet" "use2b" {
  availability_zone = "us-east-2b"
}

resource "aws_default_subnet" "use2c" {
  availability_zone = "us-east-2c"
}