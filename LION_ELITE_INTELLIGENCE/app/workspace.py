import hashlib, secrets
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from .database import Base, get_db
from .saas import OrganizationMember, SaaSUser, current_workspace

router=APIRouter(prefix="/workspace",tags=["customer-workspace"])
PAGE=Path(__file__).with_name("workspace_dashboard.html")
TEMPLATES=[("coordinator","Coordinator","Routes goals and keeps peers aligned."),("sales","Sales","Builds pipeline and improves conversion."),("operations","Operations","Designs workflows and removes bottlenecks."),("delivery","Delivery","Protects scope, quality, and outcomes."),("finance","Finance","Tracks cost, margin, and exposure."),("content","Content","Creates useful on-brand communication."),("relationships","Relationships","Maintains follow-up quality and trust."),("engineering","Engineering","Builds tested product changes."),("guardrails","Guardrails","Challenges risk and enforces approvals.")]
LIMITS={"trial":(50,3),"growth":(500,10),"scale":(5000,50)}

class WorkspaceAgent(Base):
    __tablename__="workspace_agents"; __table_args__=(UniqueConstraint("organization_id","slug"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True); organization_id:Mapped[int]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    slug:Mapped[str]=mapped_column(String(80)); name:Mapped[str]=mapped_column(String(120)); mission:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(30),default="ready"); enabled:Mapped[bool]=mapped_column(Boolean,default=True)

class WorkspaceObjective(Base):
    __tablename__="workspace_objectives"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); organization_id:Mapped[int]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    title:Mapped[str]=mapped_column(String(255)); outcome:Mapped[str]=mapped_column(Text); status:Mapped[str]=mapped_column(String(40),default="assigned")
    priority:Mapped[int]=mapped_column(Integer,default=50); owner_agent_id:Mapped[int]=mapped_column(ForeignKey("workspace_agents.id")); accountability_agent_id:Mapped[int]=mapped_column(ForeignKey("workspace_agents.id")); created_by_user_id:Mapped[int]=mapped_column(ForeignKey("saas_users.id")); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True)

class WorkspaceMessage(Base):
    __tablename__="workspace_messages"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); organization_id:Mapped[int]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    objective_id:Mapped[int]=mapped_column(ForeignKey("workspace_objectives.id",ondelete="CASCADE")); sender_agent_id:Mapped[int]=mapped_column(ForeignKey("workspace_agents.id")); message_type:Mapped[str]=mapped_column(String(40)); content:Mapped[str]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True)

class WorkspaceInvitation(Base):
    __tablename__="workspace_invitations"
    id:Mapped[int]=mapped_column(Integer,primary_key=True); organization_id:Mapped[int]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    email:Mapped[str]=mapped_column(String(255),index=True); role:Mapped[str]=mapped_column(String(30)); token_hash:Mapped[str]=mapped_column(String(64),unique=True); status:Mapped[str]=mapped_column(String(30),default="pending"); invited_by_user_id:Mapped[int]=mapped_column(ForeignKey("saas_users.id")); expires_at:Mapped[datetime]=mapped_column(DateTime)

class ObjectiveIn(BaseModel):
    title:str=Field(min_length=3,max_length=255); outcome:str=Field(min_length=8,max_length=4000); priority:int=Field(50,ge=1,le=100); owner_agent_id:int|None=None
class InviteIn(BaseModel):
    email:EmailStr; role:str=Field("member",pattern="^(admin|member|viewer)$")

def seed(db:Session,org:int):
    have={a.slug for a in db.scalars(select(WorkspaceAgent).where(WorkspaceAgent.organization_id==org))}
    for slug,name,mission in TEMPLATES:
        if slug not in have: db.add(WorkspaceAgent(organization_id=org,slug=slug,name=name,mission=mission))
    db.commit(); return list(db.scalars(select(WorkspaceAgent).where(WorkspaceAgent.organization_id==org,WorkspaceAgent.enabled.is_(True)).order_by(WorkspaceAgent.id)))
def aj(a): return {"id":a.id,"slug":a.slug,"name":a.name,"mission":a.mission,"status":a.status}

@router.get("",response_class=HTMLResponse)
def page(_=Depends(current_workspace)): return PAGE.read_text()

@router.get("/api/overview")
def overview(w=Depends(current_workspace),db:Session=Depends(get_db)):
    user,org,member=w; agents=seed(db,org.id); start=datetime.utcnow().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    used=db.scalar(select(func.count()).select_from(WorkspaceObjective).where(WorkspaceObjective.organization_id==org.id,WorkspaceObjective.created_at>=start)) or 0
    members=db.scalar(select(func.count()).select_from(OrganizationMember).where(OrganizationMember.organization_id==org.id)) or 0; ol,ml=LIMITS.get(org.plan,LIMITS["trial"])
    return {"workspace":{"name":org.name,"plan":org.plan},"viewer":{"name":user.full_name,"role":member.role},"agents":[aj(a) for a in agents],"usage":{"objectives":used,"objectives_limit":ol,"members":members,"members_limit":ml}}

@router.get("/api/objectives")
def list_objectives(w=Depends(current_workspace),db:Session=Depends(get_db)):
    _,org,_=w; agents={a.id:a for a in seed(db,org.id)}; rows=db.scalars(select(WorkspaceObjective).where(WorkspaceObjective.organization_id==org.id).order_by(WorkspaceObjective.created_at.desc()).limit(100))
    return [{"id":o.id,"title":o.title,"outcome":o.outcome,"status":o.status,"owner":aj(agents[o.owner_agent_id]),"partner":aj(agents[o.accountability_agent_id])} for o in rows]

@router.post("/api/objectives",status_code=201)
def create_objective(p:ObjectiveIn,w=Depends(current_workspace),db:Session=Depends(get_db)):
    user,org,_=w; agents=seed(db,org.id); start=datetime.utcnow().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    used=db.scalar(select(func.count()).select_from(WorkspaceObjective).where(WorkspaceObjective.organization_id==org.id,WorkspaceObjective.created_at>=start)) or 0
    if used>=LIMITS.get(org.plan,LIMITS["trial"])[0]: raise HTTPException(402,"Monthly objective limit reached")
    owner=next((a for a in agents if a.id==p.owner_agent_id),None)
    if not owner:
        text=(p.title+" "+p.outcome).lower(); route=next((s for s,keys in [("sales","sales lead prospect"),("content","content campaign brand"),("finance","cost margin budget"),("engineering","code app website"),("delivery","client quality")] if any(k in text for k in keys.split())),"operations"); owner=next(a for a in agents if a.slug==route)
    partner=next(a for a in agents if a.id!=owner.id and a.slug=="guardrails")
    item=WorkspaceObjective(organization_id=org.id,title=p.title,outcome=p.outcome,priority=p.priority,owner_agent_id=owner.id,accountability_agent_id=partner.id,created_by_user_id=user.id); db.add(item); db.flush()
    db.add_all([WorkspaceMessage(organization_id=org.id,objective_id=item.id,sender_agent_id=agents[0].id,message_type="assignment",content=f"{owner.name} owns this objective. {partner.name} is the accountability partner."),WorkspaceMessage(organization_id=org.id,objective_id=item.id,sender_agent_id=owner.id,message_type="commitment",content="I accept ownership and will provide evidence for peer review."),WorkspaceMessage(organization_id=org.id,objective_id=item.id,sender_agent_id=partner.id,message_type="accountability",content="I will challenge gaps before completion.")]); db.commit()
    return {"id":item.id,"owner":owner.name,"accountability_partner":partner.name,"status":item.status}

@router.get("/api/messages")
def messages(w=Depends(current_workspace),db:Session=Depends(get_db)):
    _,org,_=w; names={a.id:a.name for a in seed(db,org.id)}; rows=db.scalars(select(WorkspaceMessage).where(WorkspaceMessage.organization_id==org.id).order_by(WorkspaceMessage.created_at.desc()).limit(100))
    return [{"sender":names.get(m.sender_agent_id,"Member"),"type":m.message_type,"content":m.content,"created_at":m.created_at} for m in rows]

@router.get("/api/team")
def team(w=Depends(current_workspace),db:Session=Depends(get_db)):
    _,org,_=w; rows=db.execute(select(OrganizationMember,SaaSUser).join(SaaSUser,SaaSUser.id==OrganizationMember.user_id).where(OrganizationMember.organization_id==org.id)).all(); return [{"name":u.full_name,"email":u.email,"role":m.role} for m,u in rows]

@router.post("/api/invitations",status_code=201)
def invite(p:InviteIn,request:Request,w=Depends(current_workspace),db:Session=Depends(get_db)):
    user,org,member=w
    if member.role not in {"owner","admin"}: raise HTTPException(403,"Only owners and admins can invite members")
    count=db.scalar(select(func.count()).select_from(OrganizationMember).where(OrganizationMember.organization_id==org.id)) or 0
    if count>=LIMITS.get(org.plan,LIMITS["trial"])[1]: raise HTTPException(402,"Member limit reached")
    token=secrets.token_urlsafe(32); row=WorkspaceInvitation(organization_id=org.id,email=str(p.email).lower(),role=p.role,token_hash=hashlib.sha256(token.encode()).hexdigest(),invited_by_user_id=user.id,expires_at=datetime.utcnow()+timedelta(days=7)); db.add(row); db.commit()
    return {"email":row.email,"role":row.role,"invite_url":f"{str(request.base_url).rstrip('/')}/?invite={token}","expires_at":row.expires_at}
