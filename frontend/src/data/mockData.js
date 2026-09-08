export const mockUser = {
  id: 'USR-001', name: 'Demo User', email: 'demo@sixele.com',
  roles: ['Instructor', 'Assessment Officer'],
  permissions: ['courses.view','courses.edit','modules.view','modules.edit','lessons.view','lessons.edit','activities.view','activities.assess','assignments.view','assignments.grade','assessments.view','assessments.grade','assessments.rubrics.manage','submissions.view','submissions.review','submissions.return','submissions.grade','reports.view']
}

export const mockRoles = [
  { id:'role-1', name:'Super Admin', description:'Full platform administration', status:'Active', users:1, permissions:['users.manage','roles.manage','courses.create','courses.edit','courses.delete','courses.publish','settings.edit','audit.view'] },
  { id:'role-2', name:'Instructor', description:'Teaching and learner support', status:'Active', users:4, permissions:['courses.view','courses.edit','modules.view','modules.edit','lessons.view','lessons.edit','activities.view','activities.assess','assignments.grade','submissions.review','submissions.grade'] },
  { id:'role-3', name:'Assessment Officer', description:'Assessment and grading operations', status:'Active', users:2, permissions:['assessments.view','assessments.create','assessments.edit','assessments.grade','assessments.rubrics.manage','submissions.view','submissions.review','submissions.grade','reports.view'] },
]

export const dashboardStats = [
  { label:'Active Learners', value:'1,248', change:'+8.4%' },
  { label:'Published Courses', value:'42', change:'+3 this month' },
  { label:'Pending Submissions', value:'86', change:'12 need review' },
  { label:'Certificates Issued', value:'734', change:'+11.2%' },
]
