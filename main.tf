variable "public_key_path" {
  description = "The public key used to ssh to the hosts"
  default     = "./id_ed25519.pub"
}

variable "private_key_path" {
  description = "The private key used to connect to the hosts via ssh"
  default     = "./id_ed25519.pub"
}

variable "username" {
  description = "Prefix for the created AWS resources"
}

variable "redpanda_cluster_size" {
  description = "Number of redpanda nodes"
  type = number
}

variable "workload_cluster_size" {
  description = "Number of client nodes"
  type = number
}

provider "aws" {
  region = "us-west-2"
}

/////////////////////////////
resource "aws_vpc" "chaos_vpc" {
  cidr_block = "10.0.0.0/16"

  tags = {
    Name = "chaos-${var.username}"
  }
}

resource "aws_internet_gateway" "chaos" {
  vpc_id = aws_vpc.chaos_vpc.id
}

resource "aws_route" "internet_access" {
  route_table_id         = aws_vpc.chaos_vpc.main_route_table_id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.chaos.id
}

resource "aws_subnet" "chaos_subnet" {
  vpc_id                  = aws_vpc.chaos_vpc.id
  cidr_block              = "10.0.0.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "us-west-2b"
}
/////////////////////////////

resource "aws_security_group" "redpanda_kafka" {
    name = "chaos-${var.username}-security"
    vpc_id = aws_vpc.chaos_vpc.id

    ingress {
        from_port = 22
        to_port = 22
        protocol = "tcp"
        cidr_blocks = [ "0.0.0.0/0" ]
    }

    ingress {
      from_port   = 0
      to_port     = 65535
      protocol    = "tcp"
      cidr_blocks = ["10.0.0.0/16"]
    }

    egress {
        from_port        = 0
        to_port          = 0
        protocol         = "-1"
        cidr_blocks      = ["0.0.0.0/0"]
        ipv6_cidr_blocks = ["::/0"]
    }
}

resource "aws_key_pair" "ssh" {
  key_name   = "chaos-${var.username}-key"
  public_key = file(var.public_key_path)
}

resource "aws_instance" "redpanda" {
   # ubuntu 20.04
  count                  = var.redpanda_cluster_size
  ami                    = "ami-03d5c68bab01f3496"
  instance_type          = "i3.large"
  key_name               = aws_key_pair.ssh.key_name
  subnet_id              = aws_subnet.chaos_subnet.id
  vpc_security_group_ids = [aws_security_group.redpanda_kafka.id]

  tags = {
      Name = "chaos-${var.username}-redpanda"
  }

  connection {
    user        = "ubuntu"
    host        = self.public_ip
    private_key = file(var.private_key_path)
  }
}

resource "aws_instance" "client" {
   # ubuntu 20.04
  count                  = var.workload_cluster_size
  ami                    = "ami-03d5c68bab01f3496"
  instance_type          = "i3.large"
  key_name               = aws_key_pair.ssh.key_name
  subnet_id              = aws_subnet.chaos_subnet.id
  vpc_security_group_ids = [aws_security_group.redpanda_kafka.id]

  tags = {
      Name = "chaos-${var.username}-client"
  }

  connection {
    user        = "ubuntu"
    host        = self.public_ip
    private_key = file(var.private_key_path)
  }
}

resource "aws_instance" "control" {
   # ubuntu 20.04
  count                  = 1
  ami                    = "ami-03d5c68bab01f3496"
  instance_type          = "i3.large"
  key_name               = aws_key_pair.ssh.key_name
  subnet_id              = aws_subnet.chaos_subnet.id
  vpc_security_group_ids = [aws_security_group.redpanda_kafka.id]

  tags = {
      Name = "chaos-${var.username}-client"
  }

  connection {
    user        = "ubuntu"
    host        = self.public_ip
    private_key = file(var.private_key_path)
  }
}

resource "local_file" "hosts_ini" {
  content = templatefile("${path.module}/hosts_ini.tpl",
    {
      redpanda_public_ips   = aws_instance.redpanda.*.public_ip
      redpanda_private_ips  = aws_instance.redpanda.*.private_ip
      client_public_ips   = aws_instance.client.*.public_ip
      client_private_ips  = aws_instance.client.*.private_ip
      control_public_ips   = aws_instance.control.*.public_ip
      control_private_ips  = aws_instance.control.*.private_ip
      ssh_user              = "ubuntu"
    }
  )
  filename = "${path.module}/hosts.ini"
}