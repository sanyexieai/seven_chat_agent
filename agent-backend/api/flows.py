from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from database.database import get_db
from models.database_models import Flow as DBFlow
from models.database_models import FlowResponse, FlowCreate, FlowUpdate
from utils.log_helper import get_logger
import json

logger = get_logger("flows_api")

router = APIRouter(prefix="/api/flows", tags=["flows"])

@router.get("", response_model=List[FlowResponse])
async def get_flows(db: Session = Depends(get_db)):
    """获取所有流程图"""
    try:
        flows = db.query(DBFlow).filter(DBFlow.is_active == True).all()
        logger.info(f"获取到 {len(flows)} 个流程图")
        return flows
    except Exception as e:
        logger.error(f"获取流程图失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取流程图失败: {str(e)}"
        )

@router.get("/{flow_id}", response_model=FlowResponse)
async def get_flow(flow_id: int, db: Session = Depends(get_db)):
    """获取单个流程图"""
    try:
        flow = db.query(DBFlow).filter(DBFlow.id == flow_id, DBFlow.is_active == True).first()
        if not flow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="流程图不存在"
            )
        logger.info(f"获取流程图: {flow.name}")
        return flow
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取流程图失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取流程图失败: {str(e)}"
        )

@router.post("", response_model=FlowResponse)
async def create_flow(flow: FlowCreate, db: Session = Depends(get_db)):
    """创建流程图"""
    try:
        # 检查名称是否重复
        existing_flow = db.query(DBFlow).filter(
            DBFlow.name == flow.name,
            DBFlow.is_active == True
        ).first()
        
        if existing_flow:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="流程图名称已存在"
            )
        
        # 创建新流程图
        db_flow = DBFlow(
            name=flow.name,
            display_name=flow.display_name,
            description=flow.description,
            flow_config=flow.flow_config,
            is_active=True
        )
        
        db.add(db_flow)
        db.commit()
        db.refresh(db_flow)
        
        logger.info(f"创建流程图: {db_flow.name}")
        return db_flow
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建流程图失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建流程图失败: {str(e)}"
        )


@router.put("/{flow_id}", response_model=FlowResponse)
async def update_flow(flow_id: int, flow: FlowUpdate, db: Session = Depends(get_db)):
    """更新流程图"""
    try:
        db_flow = db.query(DBFlow).filter(DBFlow.id == flow_id, DBFlow.is_active == True).first()
        if not db_flow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="流程图不存在"
            )
        
        # 更新字段
        if flow.display_name is not None:
            db_flow.display_name = flow.display_name
        if flow.description is not None:
            db_flow.description = flow.description
        if flow.flow_config is not None:
            db_flow.flow_config = flow.flow_config
        
        db.commit()
        db.refresh(db_flow)
        
        logger.info(f"更新流程图: {db_flow.name}")
        return db_flow
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新流程图失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新流程图失败: {str(e)}"
        )

@router.delete("/{flow_id}")
async def delete_flow(flow_id: int, db: Session = Depends(get_db)):
    """删除流程图（硬删除）"""
    try:
        db_flow = db.query(DBFlow).filter(DBFlow.id == flow_id).first()
        if not db_flow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="流程图不存在"
            )
        
        # 硬删除
        db.delete(db_flow)
        db.commit()
        
        logger.info(f"删除流程图: {db_flow.name}")
        return {"message": "流程图删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除流程图失败: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除流程图失败: {str(e)}"
        )

@router.post("/{flow_id}/test")
async def test_flow(flow_id: int, test_data: Dict[str, Any], db: Session = Depends(get_db)):
    """测试流程图"""
    try:
        flow = db.query(DBFlow).filter(DBFlow.id == flow_id, DBFlow.is_active == True).first()
        if not flow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="流程图不存在"
            )
        
        # 这里可以调用流程图执行逻辑
        logger.info(f"测试流程图: {flow.name}")
        
        return {
            "message": "流程图测试成功",
            "flow_name": flow.name,
            "test_data": test_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试流程图失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试流程图失败: {str(e)}"
        ) 