## See live task status

$TASK_ARN = "arn:aws:ecs:us-east-1:383961856456:task/credit-real-estate-img-cluster/8a267d5ede7a447dad36bfb13e92467b"

while ($true) {
    $status = aws ecs describe-tasks `
        --cluster credit-real-estate-img-cluster `
        --tasks $TASK_ARN `
        --region us-east-1 `
        --query "tasks[0].[lastStatus, containers[0].lastStatus, containers[0].exitCode]" `
        --output text

    Write-Host "$(Get-Date -Format 'HH:mm:ss') - $status"
    Start-Sleep -Seconds 5
}

## Live logs

aws logs tail /ecs/credit-real-estate-img --follow --region us-east-1

## Run task

aws ecs run-task --cluster credit-real-estate-img-cluster --task-definition credit-real-estate-img-task:2 --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[subnet-0744e58ab45d5cc62,subnet-0d5b9e77f7c8a9d9b],securityGroups=[sg-02c631875f3673c3d],assignPublicIp=ENABLED}" --region us-east-1


## List ECR repositories

 aws ecr describe-repositories --region us-east-1 --query "repositories[*].[repositoryName, repositoryUri]" --output table