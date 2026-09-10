variable "aws_region" {
  type        = string
  description = "The AWS region to deploy resources into"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Core name prefix for project tracking resources"
  default     = "credit-real-estate-img"
}

# --- Database Variables (Kept for future use) ---
variable "db_host" {
  type        = string
  description = "PostgreSQL database hostname or connection endpoint"
  default     = ""
}

variable "db_name" {
  type        = string
  description = "Target database name"
  default     = ""
}

variable "db_user" {
  type        = string
  description = "Database administrative username"
  default     = ""
}

variable "db_password" {
  type        = string
  description = "Database user password account credential"
  sensitive   = true
  default     = ""
}

variable "db_port" {
  type        = number
  description = "Relational database connection port link"
  default     = 5432
}

# --- API Configuration ---
variable "api_url" {
  type        = string
  description = "URL to fetch property data from"
  default     = "https://8xuawsbnzg.execute-api.us-east-1.amazonaws.com/dev/data-properties"
}

# --- Image Generation Configuration ---
variable "images_quantity" {
  type        = number
  description = "Number of random properties to select for each execution"
  default     = 5
}

# --- Email Configuration ---
variable "recipient_emails" {
  type        = list(string)
  description = "List of email addresses to receive the images"
}

# --- Gmail Credentials ---
variable "gmail_user" {
  type        = string
  description = "Gmail sender account username address"
}

variable "gmail_app_password" {
  type        = string
  description = "Secure 16-character Gmail App Password token"
  sensitive   = true
}

# --- Alert Configuration ---
variable "alert_recipient" {
  type        = string
  description = "Recipient email address for execution metric status alerts"
}

# --- Fargate Resource Configuration ---
variable "fargate_cpu" {
  type        = number
  description = "CPU units for Fargate task (1024 = 1 vCPU)"
  default     = 1024
}

variable "fargate_memory" {
  type        = number
  description = "Memory in MB for Fargate task"
  default     = 2048
}

# --- S3 Storage Configuration ---
variable "s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket for storing generated property images"
  default     = "credit-real-estate-images-bucket"
}