# 权限统计与考核系统 —— 容器化部署
# 适用：Hugging Face Spaces(Docker) / 任意 Docker 主机 / Render(dockerDeploy 时)
FROM python:3.12-slim

WORKDIR /app

# 仅复制运行所需文件（保持镜像精简）
COPY app.py permission.db ./ 
COPY static ./static
COPY data ./data

# 端口：HF Spaces / 多数平台通过 PORT 环境变量注入；默认 7860
ENV PORT=7860 HOST=0.0.0.0 PYTHONUNBUFFERED=1

EXPOSE 7860

CMD ["python", "app.py"]
