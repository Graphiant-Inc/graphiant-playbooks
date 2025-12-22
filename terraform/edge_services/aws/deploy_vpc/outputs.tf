output "action_performed" {
  description = "The action that was performed (create or delete)"
  value       = var.action
}

output "stack_name" {
  description = "CloudFormation stack name"
  value       = var.stack_name
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}

# Outputs for graphiant_stack create action
output "graphiant_stack_id" {
  description = "graphiant_stack stack ID (only available when action is 'create')"
  value       = var.action == "create" ? try(aws_cloudformation_stack.graphiant_stack[0].id, null) : null
}

output "graphiant_stack_outputs" {
  description = "graphiant_stack stack outputs (only available when action is 'create')"
  value       = var.action == "create" ? try(aws_cloudformation_stack.graphiant_stack[0].outputs, null) : null
}

# Outputs for graphiant_stack delete action
output "graphiant_stack_deleted" {
  description = "Confirmation that stack deletion was prepared (only available when action is 'delete')"
  value       = var.action == "delete" ? "Stack ${var.stack_name} deletion prepared" : null
}
