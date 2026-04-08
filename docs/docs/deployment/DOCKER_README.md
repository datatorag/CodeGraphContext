# 🐳 Docker Setup - Quick Reference

This is a quick reference guide for Docker deployment. For detailed information, see the comprehensive guides.

## 📚 Documentation Files

- **`DOCKER_SUMMARY.md`** - Complete overview of Docker packaging
- **`DOCKER_DEPLOYMENT.md`** - Detailed deployment instructions
- **`HOSTING_COMPARISON.md`** - Compare 15+ hosting options
- **`DEPLOYMENT_CHECKLIST.md`** - Step-by-step deployment checklist
- **`k8s/README.md`** - Kubernetes deployment guide

## 🚀 Quick Start (3 Options)

### Option 1: Automated Setup (Recommended)
```bash
./docker-quickstart.sh
```

### Option 2: Docker Compose
```bash
cp docker-compose.template.yml docker-compose.yml
docker-compose up -d
docker-compose exec codegraphcontext bash
```

### Option 3: Docker Only
```bash
docker build -t codegraphcontext:latest .
docker run -it --rm -v $(pwd):/workspace codegraphcontext:latest bash
```

## 🌐 Production Deployment

### Automated Production Setup
```bash
# On your cloud VM (Ubuntu/Debian)
./deploy-production.sh
```

### Manual Production Setup
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Clone and deploy
git clone https://github.com/CodeGraphContext/CodeGraphContext.git
cd CodeGraphContext
./docker-quickstart.sh
```

## 💰 Hosting Recommendations

| Use Case | Provider | Cost | Setup |
|----------|----------|------|-------|
| **Hobby** | Railway.app | Free | Very Easy |
| **Production** | DigitalOcean | $12-24/mo | Easy |
| **Enterprise** | Kubernetes | $50+/mo | Hard |
| **Budget** | Oracle Cloud | Free | Medium |

See `HOSTING_COMPARISON.md` for detailed comparison of 15+ options.

## 📦 What's Included

✅ Multi-stage Dockerfile (optimized for size)
✅ Docker Compose with Neo4j
✅ Kubernetes manifests (production-ready)
✅ GitHub Actions (automated builds)
✅ Quick-start script (interactive setup)
✅ Production deployment script (full automation)
✅ Comprehensive documentation
✅ Architecture diagram

## 🔧 Common Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f codegraphcontext

# Access container
docker-compose exec codegraphcontext bash

# Stop services
docker-compose down

# Rebuild
docker-compose build --no-cache

# With Neo4j
docker-compose --profile neo4j up -d
```

## 🗄️ Database Options

### FalkorDB Lite (Default)
- Built-in, no setup required
- Perfect for development
- Lightweight and fast

### Neo4j (Production)
```bash
docker-compose --profile neo4j up -d
# Then configure: cgc neo4j setup
# URI: bolt://neo4j:7687
# User: neo4j
# Pass: codegraph123
```

## 📊 Resource Requirements

| Environment | CPU | RAM | Storage |
|-------------|-----|-----|---------|
| Development | 1 core | 2GB | 10GB |
| Production | 2-4 cores | 4-8GB | 20-50GB |
| Large Scale | 4+ cores | 8-16GB | 50-100GB |

## 🔒 Security Checklist

- [ ] Change default Neo4j password
- [ ] Configure firewall rules
- [ ] Enable HTTPS/TLS
- [ ] Set up automated backups
- [ ] Use environment variables for secrets
- [ ] Regular security updates

## 🆘 Troubleshooting

### Container won't start
```bash
docker-compose logs codegraphcontext
docker-compose build --no-cache
```

### Database connection issues
```bash
docker-compose ps
docker-compose logs neo4j
```

### Out of memory
```bash
# Edit docker-compose.yml
deploy:
  resources:
    limits:
      memory: 4G
```

## 📈 Next Steps

1. **Local Testing:** Run `./docker-quickstart.sh`
2. **Choose Hosting:** Review `HOSTING_COMPARISON.md`
3. **Deploy:** Follow `DOCKER_DEPLOYMENT.md`
4. **Checklist:** Use `DEPLOYMENT_CHECKLIST.md`
5. **Monitor:** Set up logging and backups

## 🎯 Recommended Path

```
Local Development (Docker)
    ↓
Test on Railway.app (Free)
    ↓
Production on DigitalOcean ($12/mo)
    ↓
Scale with Kubernetes (as needed)
```

## 📞 Support

- **Documentation:** See files listed above
- **GitHub Issues:** https://github.com/CodeGraphContext/CodeGraphContext/issues
- **Discord:** https://discord.gg/dR4QY32uYQ
- **Website:** http://codegraphcontext.vercel.app/

## 🎉 You're Ready!

Everything you need is here. Start with `./docker-quickstart.sh` and refer to the detailed guides as needed.

**Happy deploying! 🚀**
