variable "region" {
  type        = string
  default     = "eu-west-1"
  description = "Public data with no residency need, so a cheaper region than af-south-1."
}

variable "alert_email" {
  type        = string
  description = "Where budget alerts go. Set it in terraform.tfvars, which git ignores."
}

variable "monthly_budget_usd" {
  type        = number
  default     = 10
  description = "Alert level for monthly spend before credits. It alerts; it does not stop spend."
}
