resource "aws_security_group" "db_sg" {
  name    = "gha-test-repo-db-sg"
  description = "Created by RDS management console"
  vpc_id  = "vpc-0f3bf3667d5fedbd0"

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    security_groups = ["sg-062d1672a4231f4f3"]
  }

  egress {
    from_port   = 0
    to_port     = 0 
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "alb_sg" {
  name        = "gha-test-repo-alb-sg"
  description = "gha-test-repo-alb-sg"
  vpc_id      = "vpc-0f3bf3667d5fedbd0"

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "app_sg" {
  name        = "gha-test-repo-app-sg"
  description = "gha-test-repo-app-sg"
  vpc_id      = "vpc-0f3bf3667d5fedbd0"

  ingress {
    from_port       = 5000
    to_port         = 5000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

